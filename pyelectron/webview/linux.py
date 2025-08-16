"""
PyElectron WebView Linux Implementation

This module provides WebView implementation for Linux using WebKit2GTK
through PyGObject bindings.
"""

import asyncio
import json
from typing import Any, Optional

try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.0')
    
    from gi.repository import Gtk, WebKit2, GLib, Gdk
    GTK_AVAILABLE = True
except (ImportError, ValueError) as e:
    GTK_AVAILABLE = False
    Gtk = None
    WebKit2 = None

from .base import BaseWebView, WebViewConfig, WebViewState, WebViewEventType, SecurityPolicy
from pyelectron.utils.errors import WebViewError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)

if not GTK_AVAILABLE:
    logger.warning("WebKit2GTK not available on Linux")


class LinuxWebView(BaseWebView):
    """
    Linux WebView implementation using WebKit2GTK.
    
    Provides native Linux WebView functionality with security policies
    and PyElectron IPC integration using PyGObject.
    """
    
    def __init__(self, webview_id: str, config: WebViewConfig):
        if not GTK_AVAILABLE:
            raise WebViewError(
                "WebKit2GTK not available. Please install:\n"
                "Ubuntu/Debian: sudo apt install python3-gi webkit2gtk-4.0\n"
                "Fedora: sudo dnf install python3-gobject webkit2gtk4\n"
                "Arch: sudo pacman -S python-gobject webkit2gtk\n"
                "Then: pip install PyGObject"
            )
        
        super().__init__(webview_id, config)
        
        # GTK/WebKit objects
        self.window: Optional[Gtk.Window] = None
        self.webview: Optional[WebKit2.WebView] = None
        self.context: Optional[WebKit2.WebContext] = None
        self.settings: Optional[WebKit2.Settings] = None
        
        # Event handling
        self._ready_event = asyncio.Event()
        
        logger.debug(f"Linux WebView {webview_id} initialized")
    
    @handle_exception
    async def create(self) -> None:
        """Create the native WebKit2GTK instance."""
        if self.webview is not None:
            raise WebViewError("WebView already created")
        
        logger.info(f"Creating Linux WebView: {self.webview_id}")
        
        # Initialize GTK if not already done
        if not Gtk.init_check():
            raise WebViewError("Failed to initialize GTK")
        
        # Create WebKit context and configure security
        self.context = WebKit2.WebContext.new()
        self._configure_security()
        
        # Create WebView with context
        self.webview = WebKit2.WebView.new_with_context(self.context)
        
        # Configure WebView settings
        self.settings = self.webview.get_settings()
        self._apply_webview_settings()
        
        # Set up IPC if enabled
        if self.config.enable_pyelectron_api:
            self._setup_ipc_bridge()
        
        # Create GTK window
        self.window = Gtk.Window()
        self.window.set_title(self.config.title)
        self.window.set_default_size(self.config.width, self.config.height)
        
        # Configure window properties
        if not self.config.resizable:
            self.window.set_resizable(False)
        
        if self.config.always_on_top:
            self.window.set_keep_above(True)
        
        if self.config.fullscreen:
            self.window.fullscreen()
        
        # Add WebView to window
        self.window.add(self.webview)
        
        # Connect signals
        self._connect_signals()
        
        self.state = WebViewState.CREATED
        
        # Load initial content
        if self.config.url:
            await self.load_url(self.config.url)
        elif self.config.html:
            await self.load_html(self.config.html)
        
        await self.emit_event(WebViewEventType.READY)
        logger.info(f"Linux WebView created successfully: {self.webview_id}")
    
    def _configure_security(self) -> None:
        """Configure WebKit security settings."""
        security_config = self._apply_security_config()
        
        # Configure security manager
        security_manager = self.context.get_security_manager()
        
        # Set up data manager for privacy
        if self.config.security_policy == SecurityPolicy.STRICT:
            # Use ephemeral data manager
            data_manager = WebKit2.WebsiteDataManager.new_ephemeral()
            self.context.set_website_data_manager(data_manager)
        
        # Configure TLS policy
        if self.config.security_policy != SecurityPolicy.PERMISSIVE:
            self.context.set_tls_errors_policy(WebKit2.TLSErrorsPolicy.FAIL)
        
        logger.debug(f"Security configured for {self.config.security_policy.value} policy")
    
    def _apply_webview_settings(self) -> None:
        """Apply WebView settings based on configuration."""
        security_config = self._apply_security_config()
        
        # JavaScript settings
        self.settings.set_enable_javascript(security_config['enable_javascript'])
        self.settings.set_enable_javascript_markup(security_config['enable_javascript'])
        
        # Plugin settings
        self.settings.set_enable_plugins(security_config['enable_plugins'])
        
        # Developer tools
        self.settings.set_enable_developer_extras(security_config['enable_dev_tools'])
        
        # Storage settings
        if self.config.security_policy == SecurityPolicy.STRICT:
            self.settings.set_enable_offline_web_application_cache(False)
            self.settings.set_enable_page_cache(False)
        else:
            self.settings.set_enable_offline_web_application_cache(True)
            self.settings.set_enable_page_cache(True)
        
        # Media settings
        self.settings.set_enable_media_stream(
            self.config.security_policy != SecurityPolicy.STRICT
        )
        
        # User agent
        if self.config.user_agent:
            self.settings.set_user_agent(self.config.user_agent)
        
        logger.debug("WebView settings applied")
    
    def _setup_ipc_bridge(self) -> None:
        """Set up IPC bridge for PyElectron API."""
        user_content_manager = self.webview.get_user_content_manager()
        
        # Register script message handler
        user_content_manager.register_script_message_handler(self.config.ipc_namespace)
        user_content_manager.connect(
            f"script-message-received::{self.config.ipc_namespace}",
            self._on_script_message
        )
        
        # Inject PyElectron API script
        api_script = self._generate_api_script()
        user_script = WebKit2.UserScript.new(
            api_script,
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.START,
            None,  # No whitelist
            None   # No blacklist
        )
        user_content_manager.add_script(user_script)
        
        logger.debug("IPC bridge configured")
    
    def _generate_api_script(self) -> str:
        """Generate JavaScript API for PyElectron integration."""
        namespace = self.config.ipc_namespace
        
        return f"""
        (function() {{
            // Create PyElectron API namespace
            window.{namespace} = {{
                // Send IPC message to Python
                send: function(method, params) {{
                    window.webkit.messageHandlers.{namespace}.postMessage({{
                        type: 'pyelectron_ipc',
                        method: method,
                        params: params || null,
                        id: Math.random().toString(36).substr(2, 9)
                    }});
                }},
                
                // Log message (for debugging)
                log: function(message) {{
                    window.webkit.messageHandlers.{namespace}.postMessage({{
                        type: 'console_log',
                        message: message
                    }});
                }},
                
                // Platform information
                platform: 'linux',
                version: '{self.webview_id}'
            }};
            
            // Custom CSS injection
            {self._get_custom_css_script()}
            
            // Mark PyElectron as ready
            document.addEventListener('DOMContentLoaded', function() {{
                window.{namespace}.ready = true;
                window.dispatchEvent(new Event('pyelectron:ready'));
            }});
        }})();
        """
    
    def _get_custom_css_script(self) -> str:
        """Generate custom CSS injection script."""
        if not self.config.custom_css:
            return ""
        
        css = self.config.custom_css.replace('\\', '\\\\').replace('"', '\\"')
        return f"""
        var style = document.createElement('style');
        style.textContent = "{css}";
        document.head.appendChild(style);
        """
    
    def _connect_signals(self) -> None:
        """Connect GTK/WebKit signals."""
        # Window signals
        self.window.connect("destroy", self._on_window_destroy)
        self.window.connect("delete-event", self._on_window_delete)
        
        # WebView signals
        self.webview.connect("load-changed", self._on_load_changed)
        self.webview.connect("load-failed", self._on_load_failed)
        self.webview.connect("notify::title", self._on_title_changed)
        
        # Context menu (if disabled)
        if not self.config.enable_context_menu:
            self.webview.connect("context-menu", lambda *args: True)
    
    def _on_script_message(self, content_manager, result):
        """Handle script message from JavaScript."""
        try:
            # Get message value
            js_value = result.get_js_value()
            if js_value.is_object():
                # Convert to Python dict
                message = self._js_value_to_dict(js_value)
                
                if message.get('type') == 'pyelectron_ipc':
                    asyncio.create_task(self._handle_ipc_message(message))
                else:
                    asyncio.create_task(self.emit_event(
                        WebViewEventType.CONSOLE_MESSAGE,
                        {'message': str(message)}
                    ))
        except Exception as e:
            logger.error(f"Error handling script message: {e}")
    
    def _js_value_to_dict(self, js_value) -> dict:
        """Convert WebKit JavaScript value to Python dict."""
        # This is a simplified conversion
        # In a real implementation, this would handle all JS types
        try:
            return json.loads(js_value.to_string())
        except:
            return {'value': js_value.to_string()}
    
    async def _handle_ipc_message(self, message: dict) -> None:
        """Handle IPC message from JavaScript."""
        try:
            method = message.get('method')
            params = message.get('params')
            
            # Emit as console message for now
            await self.emit_event(WebViewEventType.CONSOLE_MESSAGE, {
                'type': 'ipc',
                'method': method,
                'params': params
            })
            
        except Exception as e:
            logger.error(f"Error handling IPC message: {e}")
    
    def _on_load_changed(self, webview, load_event):
        """Handle load state changes."""
        if load_event == WebKit2.LoadEvent.STARTED:
            self.state = WebViewState.LOADING
            asyncio.create_task(self.emit_event(WebViewEventType.NAVIGATION_START))
        
        elif load_event == WebKit2.LoadEvent.FINISHED:
            self.state = WebViewState.LOADED
            asyncio.create_task(self.emit_event(WebViewEventType.NAVIGATION_COMPLETE))
            
            # Inject custom JS if configured
            if self.config.custom_js:
                asyncio.create_task(self.execute_javascript(self.config.custom_js))
    
    def _on_load_failed(self, webview, load_event, uri, error):
        """Handle load failures."""
        self.state = WebViewState.ERROR
        asyncio.create_task(self.emit_event(
            WebViewEventType.NAVIGATION_ERROR,
            {'url': uri, 'error': str(error)}
        ))
    
    def _on_title_changed(self, webview, param):
        """Handle title changes."""
        title = webview.get_title()
        asyncio.create_task(self.emit_event(
            WebViewEventType.TITLE_CHANGED,
            {'title': title}
        ))
    
    def _on_window_destroy(self, window):
        """Handle window destroy."""
        self.state = WebViewState.DESTROYED
        asyncio.create_task(self.emit_event(WebViewEventType.CLOSE_REQUESTED))
    
    def _on_window_delete(self, window, event):
        """Handle window delete event."""
        # Return False to allow deletion
        return False
    
    @handle_exception
    async def load_url(self, url: str) -> None:
        """Load a URL in the WebView."""
        if not self.webview:
            raise WebViewError("WebView not created")
        
        if not self._validate_url(url):
            raise WebViewError(f"URL not allowed by security policy: {url}")
        
        logger.debug(f"Loading URL: {url}")
        self.state = WebViewState.LOADING
        
        self.webview.load_uri(url)
    
    @handle_exception
    async def load_html(self, html: str, base_url: Optional[str] = None) -> None:
        """Load HTML content in the WebView."""
        if not self.webview:
            raise WebViewError("WebView not created")
        
        logger.debug("Loading HTML content")
        self.state = WebViewState.LOADING
        
        if base_url:
            self.webview.load_html(html, base_url)
        else:
            self.webview.load_html(html, "file://")
    
    @handle_exception
    async def execute_javascript(self, script: str) -> Any:
        """Execute JavaScript in the WebView and return result."""
        if not self.webview:
            raise WebViewError("WebView not created")
        
        logger.debug(f"Executing JavaScript: {script[:100]}...")
        
        # Create future for result
        future = asyncio.get_event_loop().create_future()
        
        def on_script_finished(webview, result, user_data):
            try:
                js_result = webview.run_javascript_finish(result)
                if js_result:
                    js_value = js_result.get_js_value()
                    value = self._js_value_to_python(js_value)
                    future.set_result(value)
                else:
                    future.set_result(None)
            except Exception as e:
                future.set_exception(WebViewError(f"JavaScript error: {str(e)}"))
        
        # Execute script
        self.webview.run_javascript(script, None, on_script_finished, None)
        
        return await future
    
    def _js_value_to_python(self, js_value) -> Any:
        """Convert WebKit JavaScript value to Python value."""
        if js_value.is_string():
            return js_value.to_string()
        elif js_value.is_number():
            return js_value.to_double()
        elif js_value.is_boolean():
            return js_value.to_boolean()
        elif js_value.is_null() or js_value.is_undefined():
            return None
        else:
            return js_value.to_string()
    
    @handle_exception
    async def show(self) -> None:
        """Show the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        self.window.show_all()
        logger.debug(f"WebView window shown: {self.webview_id}")
    
    @handle_exception
    async def hide(self) -> None:
        """Hide the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        self.window.hide()
        logger.debug(f"WebView window hidden: {self.webview_id}")
    
    @handle_exception
    async def close(self) -> None:
        """Close the WebView and cleanup resources."""
        logger.info(f"Closing Linux WebView: {self.webview_id}")
        
        self.state = WebViewState.DESTROYED
        
        if self.window:
            self.window.destroy()
            self.window = None
        
        if self.webview:
            self.webview = None
        
        self.context = None
        self.settings = None
        
        logger.info(f"Linux WebView closed: {self.webview_id}")
    
    @handle_exception
    async def resize(self, width: int, height: int) -> None:
        """Resize the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        self.window.resize(width, height)
        logger.debug(f"WebView resized to {width}x{height}")
    
    @handle_exception
    async def get_url(self) -> Optional[str]:
        """Get the current URL."""
        if not self.webview:
            return None
        
        return self.webview.get_uri()
    
    @handle_exception
    async def get_title(self) -> Optional[str]:
        """Get the current page title."""
        if not self.webview:
            return None
        
        return self.webview.get_title()
    
    def set_security_policy(self, policy: SecurityPolicy) -> None:
        """Configure security policy for the WebView."""
        self.config.security_policy = policy
        
        if self.webview:
            logger.warning("Security policy changed after WebView creation - restart required for full effect")
        
        logger.debug(f"Security policy set to: {policy.value}")


# Register the Linux backend
if GTK_AVAILABLE:
    from .base import WebViewFactory
    WebViewFactory.register_backend("Linux", LinuxWebView)