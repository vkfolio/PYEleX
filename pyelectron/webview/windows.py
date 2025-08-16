"""
PyElectron WebView Windows Implementation

This module provides WebView implementation for Windows using WebView2
through pywebview library with CEF backend.
"""

import asyncio
import json
from typing import Any, Optional

try:
    import webview
    import webview.platforms.cef as cef
    WEBVIEW_AVAILABLE = True
except ImportError as e:
    WEBVIEW_AVAILABLE = False
    webview = None

from .base import BaseWebView, WebViewConfig, WebViewState, WebViewEventType, SecurityPolicy
from pyelectron.utils.errors import WebViewError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)

if not WEBVIEW_AVAILABLE:
    logger.warning("WebView not available on Windows")


class WindowsWebView(BaseWebView):
    """
    Windows WebView implementation using WebView2/CEF.
    
    Provides native Windows WebView functionality with security policies
    and PyElectron IPC integration using pywebview library.
    """
    
    def __init__(self, webview_id: str, config: WebViewConfig):
        if not WEBVIEW_AVAILABLE:
            raise WebViewError(
                "WebView not available. Please install: "
                "pip install pywebview[cef]"
            )
        
        super().__init__(webview_id, config)
        
        # WebView instance
        self.window = None
        self.api_instance = None
        
        # Event handling
        self._ready_event = asyncio.Event()
        self._closed_event = asyncio.Event()
        
        logger.debug(f"Windows WebView {webview_id} initialized")
    
    @handle_exception
    async def create(self) -> None:
        """Create the native WebView2 instance."""
        if self.window is not None:
            raise WebViewError("WebView already created")
        
        logger.info(f"Creating Windows WebView: {self.webview_id}")
        
        # Configure security settings
        security_config = self._apply_security_config()
        
        # Create PyElectron API instance for IPC
        if self.config.enable_pyelectron_api:
            self.api_instance = PyElectronAPI(self)
        
        # Configure webview options
        webview_options = {
            'debug': security_config['enable_dev_tools'],
            'js_api': self.api_instance if self.api_instance else None,
            'resizable': self.config.resizable,
            'minimizable': self.config.minimizable,
            'maximizable': self.config.maximizable,
            'on_top': self.config.always_on_top,
            'fullscreen': self.config.fullscreen,
        }
        
        # Determine initial URL or HTML
        initial_url = self.config.url
        if not initial_url and self.config.html:
            # For HTML content, we'll load it after window creation
            initial_url = 'about:blank'
        elif not initial_url:
            initial_url = 'about:blank'
        
        # Create webview window
        self.window = webview.create_window(
            title=self.config.title,
            url=initial_url,
            width=self.config.width,
            height=self.config.height,
            **webview_options
        )
        
        # Set up event callbacks
        self.window.events.loaded += self._on_loaded
        self.window.events.closing += self._on_closing
        
        # Configure user agent if specified
        if self.config.user_agent:
            # Note: User agent setting depends on webview implementation
            pass
        
        self.state = WebViewState.CREATED
        
        # Start webview in background thread
        def start_webview():
            try:
                webview.start(debug=security_config['enable_dev_tools'])
            except Exception as e:
                logger.error(f"Error starting webview: {e}")
        
        # Run webview in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, start_webview)
        
        # Wait for ready event
        await self._ready_event.wait()
        
        # Load custom content if needed
        if self.config.html and not self.config.url:
            await self.load_html(self.config.html)
        
        await self.emit_event(WebViewEventType.READY)
        logger.info(f"Windows WebView created successfully: {self.webview_id}")
    
    def _on_loaded(self):
        """Called when WebView finishes loading."""
        self.state = WebViewState.LOADED
        self._ready_event.set()
        
        # Inject custom CSS and JS
        if self.config.custom_css or self.config.custom_js:
            asyncio.create_task(self._inject_custom_content())
        
        # Emit navigation complete event
        asyncio.create_task(self.emit_event(WebViewEventType.NAVIGATION_COMPLETE))
    
    def _on_closing(self):
        """Called when WebView is about to close."""
        self.state = WebViewState.DESTROYED
        self._closed_event.set()
        asyncio.create_task(self.emit_event(WebViewEventType.CLOSE_REQUESTED))
    
    async def _inject_custom_content(self):
        """Inject custom CSS and JavaScript."""
        try:
            if self.config.custom_css:
                css_script = f"""
                var style = document.createElement('style');
                style.textContent = {json.dumps(self.config.custom_css)};
                document.head.appendChild(style);
                """
                await self.execute_javascript(css_script)
            
            if self.config.custom_js:
                await self.execute_javascript(self.config.custom_js)
                
        except Exception as e:
            logger.error(f"Error injecting custom content: {e}")
    
    @handle_exception
    async def load_url(self, url: str) -> None:
        """Load a URL in the WebView."""
        if not self.window:
            raise WebViewError("WebView not created")
        
        if not self._validate_url(url):
            raise WebViewError(f"URL not allowed by security policy: {url}")
        
        logger.debug(f"Loading URL: {url}")
        self.state = WebViewState.LOADING
        
        # Load URL in webview
        self.window.load_url(url)
        
        await self.emit_event(WebViewEventType.NAVIGATION_START, {'url': url})
    
    @handle_exception
    async def load_html(self, html: str, base_url: Optional[str] = None) -> None:
        """Load HTML content in the WebView."""
        if not self.window:
            raise WebViewError("WebView not created")
        
        logger.debug("Loading HTML content")
        self.state = WebViewState.LOADING
        
        # Load HTML in webview
        self.window.load_html(html)
        
        await self.emit_event(WebViewEventType.NAVIGATION_START, {'html': True})
    
    @handle_exception
    async def execute_javascript(self, script: str) -> Any:
        """Execute JavaScript in the WebView and return result."""
        if not self.window:
            raise WebViewError("WebView not created")
        
        logger.debug(f"Executing JavaScript: {script[:100]}...")
        
        try:
            # Execute JavaScript and wait for result
            result = self.window.evaluate_js(script)
            return result
        except Exception as e:
            raise WebViewError(f"JavaScript execution error: {str(e)}")
    
    @handle_exception
    async def show(self) -> None:
        """Show the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        # Note: pywebview windows are shown by default
        # This could be implemented with platform-specific window management
        logger.debug(f"WebView window shown: {self.webview_id}")
    
    @handle_exception
    async def hide(self) -> None:
        """Hide the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        # Note: pywebview doesn't have direct hide method
        # This could be implemented with platform-specific window management
        logger.debug(f"WebView window hidden: {self.webview_id}")
    
    @handle_exception
    async def close(self) -> None:
        """Close the WebView and cleanup resources."""
        logger.info(f"Closing Windows WebView: {self.webview_id}")
        
        self.state = WebViewState.DESTROYED
        
        if self.window:
            # Close webview window
            self.window.destroy()
            self.window = None
        
        # Clean up API instance
        self.api_instance = None
        
        # Wait for close event
        await self._closed_event.wait()
        
        logger.info(f"Windows WebView closed: {self.webview_id}")
    
    @handle_exception
    async def resize(self, width: int, height: int) -> None:
        """Resize the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        # Note: pywebview doesn't have direct resize method
        # This could be implemented with platform-specific window management
        logger.debug(f"WebView resize requested to {width}x{height}")
    
    @handle_exception
    async def get_url(self) -> Optional[str]:
        """Get the current URL."""
        if not self.window:
            return None
        
        try:
            # Get current URL from window
            result = await self.execute_javascript("window.location.href")
            return result if result != "about:blank" else None
        except:
            return None
    
    @handle_exception
    async def get_title(self) -> Optional[str]:
        """Get the current page title."""
        if not self.window:
            return None
        
        try:
            # Get document title
            result = await self.execute_javascript("document.title")
            return result if result else None
        except:
            return None
    
    def set_security_policy(self, policy: SecurityPolicy) -> None:
        """Configure security policy for the WebView."""
        self.config.security_policy = policy
        
        if self.window:
            logger.warning("Security policy changed after WebView creation - restart required for full effect")
        
        logger.debug(f"Security policy set to: {policy.value}")


class PyElectronAPI:
    """
    JavaScript API for PyElectron integration on Windows.
    
    This class is exposed to JavaScript and provides IPC functionality
    between the WebView and Python backend.
    """
    
    def __init__(self, webview_instance: WindowsWebView):
        self.webview = webview_instance
        self.namespace = webview_instance.config.ipc_namespace
        
        logger.debug("PyElectron API initialized for Windows WebView")
    
    def send(self, method: str, params: Any = None) -> str:
        """
        Send IPC message to Python backend.
        
        Called from JavaScript as: pyelectron.send('method_name', params)
        """
        try:
            # Handle IPC message
            message = {
                'type': 'pyelectron_ipc',
                'method': method,
                'params': params,
                'webview_id': self.webview.webview_id
            }
            
            # For now, emit as console message
            # In full implementation, this would route to IPC system
            asyncio.create_task(self.webview.emit_event(
                WebViewEventType.CONSOLE_MESSAGE,
                message
            ))
            
            return "message_sent"
            
        except Exception as e:
            logger.error(f"Error in PyElectron API send: {e}")
            return f"error: {str(e)}"
    
    def log(self, message: str) -> None:
        """Log message from JavaScript."""
        asyncio.create_task(self.webview.emit_event(
            WebViewEventType.CONSOLE_MESSAGE,
            {'message': str(message), 'type': 'log'}
        ))
    
    def get_platform(self) -> str:
        """Get platform information."""
        return "win32"
    
    def get_version(self) -> str:
        """Get PyElectron version."""
        return self.webview.webview_id
    
    def is_ready(self) -> bool:
        """Check if PyElectron API is ready."""
        return self.webview.state in [WebViewState.LOADED, WebViewState.CREATED]


# Register the Windows backend
if WEBVIEW_AVAILABLE:
    from .base import WebViewFactory
    WebViewFactory.register_backend("Windows", WindowsWebView)