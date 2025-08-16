"""
PyElectron WebView macOS Backend

This module contains the actual macOS WebView implementation that is only
loaded when WebKit is available.
"""

import asyncio
import json
from typing import Any, Optional

import objc
from Foundation import NSObject, NSString, NSURL, NSURLRequest
from WebKit import (
    WKWebView, WKWebViewConfiguration, WKUserContentController,
    WKUserScript, WKUserScriptInjectionTime, WKNavigationDelegate,
    WKUIDelegate, WKScriptMessageHandler, WKWebsiteDataStore,
    WKPreferences, WKProcessPool
)
from AppKit import NSWindow, NSView, NSApplication, NSRect, NSWindowStyleMask

from .base import BaseWebView, WebViewConfig, WebViewState, WebViewEventType, SecurityPolicy
from pyelectron.utils.errors import WebViewError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class PyElectronScriptMessageHandler(NSObject):
    """Handler for JavaScript messages from WebView."""
    
    def initWithWebView_(self, webview):
        """Initialize with reference to PyElectron WebView."""
        self = objc.super(PyElectronScriptMessageHandler, self).init()
        if self is None:
            return None
        
        self.webview = webview
        return self
    
    def userContentController_didReceiveScriptMessage_(self, controller, message):
        """Handle script message from JavaScript."""
        try:
            # Parse message from JavaScript
            body = message.body()
            
            if isinstance(body, dict) and body.get('type') == 'pyelectron_ipc':
                # Handle IPC message
                asyncio.create_task(self.webview._handle_ipc_message(body))
            else:
                # Handle regular console message
                asyncio.create_task(self.webview.emit_event(
                    WebViewEventType.CONSOLE_MESSAGE,
                    {'message': str(body)}
                ))
                
        except Exception as e:
            logger.error(f"Error handling script message: {e}")


class PyElectronNavigationDelegate(NSObject):
    """Navigation delegate for WebView."""
    
    def initWithWebView_(self, webview):
        """Initialize with reference to PyElectron WebView."""
        self = objc.super(PyElectronNavigationDelegate, self).init()
        if self is None:
            return None
        
        self.webview = webview
        return self
    
    def webView_didStartProvisionalNavigation_(self, webview, navigation):
        """Called when navigation starts."""
        asyncio.create_task(self.webview.emit_event(
            WebViewEventType.NAVIGATION_START,
            {'url': str(webview.URL()) if webview.URL() else None}
        ))
    
    def webView_didFinishNavigation_(self, webview, navigation):
        """Called when navigation completes successfully."""
        self.webview.state = WebViewState.LOADED
        asyncio.create_task(self.webview.emit_event(
            WebViewEventType.NAVIGATION_COMPLETE,
            {'url': str(webview.URL()) if webview.URL() else None}
        ))
    
    def webView_didFailProvisionalNavigation_withError_(self, webview, navigation, error):
        """Called when navigation fails."""
        self.webview.state = WebViewState.ERROR
        asyncio.create_task(self.webview.emit_event(
            WebViewEventType.NAVIGATION_ERROR,
            {
                'url': str(webview.URL()) if webview.URL() else None,
                'error': str(error.localizedDescription())
            }
        ))
    
    def webView_decidePolicyForNavigationAction_decisionHandler_(self, webview, action, handler):
        """Decide whether to allow navigation."""
        url = str(action.request().URL())
        
        # Validate URL against security policy
        if not self.webview._validate_url(url):
            handler(0)  # Cancel navigation
            return
        
        handler(1)  # Allow navigation


class PyElectronUIDelegate(NSObject):
    """UI delegate for WebView."""
    
    def initWithWebView_(self, webview):
        """Initialize with reference to PyElectron WebView."""
        self = objc.super(PyElectronUIDelegate, self).init()
        if self is None:
            return None
        
        self.webview = webview
        return self
    
    def webView_runJavaScriptAlertPanelWithMessage_initiatedByFrame_completionHandler_(
        self, webview, message, frame, handler):
        """Handle JavaScript alert."""
        asyncio.create_task(self.webview.emit_event(
            WebViewEventType.ALERT,
            {'message': str(message)}
        ))
        handler()  # Dismiss alert
    
    def webViewDidClose_(self, webview):
        """Handle WebView close."""
        asyncio.create_task(self.webview.emit_event(WebViewEventType.CLOSE_REQUESTED))


class macOSWebView(BaseWebView):
    """macOS WebView implementation using WKWebView."""
    
    def __init__(self, webview_id: str, config: WebViewConfig):
        super().__init__(webview_id, config)
        
        # Native objects
        self.window: Optional[NSWindow] = None
        self.webview: Optional[WKWebView] = None
        self.configuration: Optional[WKWebViewConfiguration] = None
        
        # Delegates
        self.navigation_delegate = None
        self.ui_delegate = None
        self.script_handler = None
        
        logger.debug(f"macOS WebView {webview_id} initialized")
    
    @handle_exception
    async def create(self) -> None:
        """Create the native WKWebView instance."""
        if self.webview is not None:
            raise WebViewError("WebView already created")
        
        logger.info(f"Creating macOS WebView: {self.webview_id}")
        
        # Create WebView configuration
        self.configuration = WKWebViewConfiguration.alloc().init()
        
        # Configure security and preferences
        self._configure_security()
        
        # Set up user content controller for IPC
        if self.config.enable_pyelectron_api:
            self._setup_ipc_bridge()
        
        # Create WebView
        frame = NSRect((0, 0), (self.config.width, self.config.height))
        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            frame, self.configuration
        )
        
        # Set up delegates
        self.navigation_delegate = PyElectronNavigationDelegate.alloc().initWithWebView_(self)
        self.ui_delegate = PyElectronUIDelegate.alloc().initWithWebView_(self)
        
        self.webview.setNavigationDelegate_(self.navigation_delegate)
        self.webview.setUIDelegate_(self.ui_delegate)
        
        # Create window
        style_mask = (
            NSWindowStyleMask.NSTitledWindowMask |
            NSWindowStyleMask.NSClosableWindowMask |
            (NSWindowStyleMask.NSMiniaturizableWindowMask if self.config.minimizable else 0) |
            (NSWindowStyleMask.NSResizableWindowMask if self.config.resizable else 0)
        )
        
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style_mask, 2, False
        )
        
        self.window.setTitle_(NSString.stringWithString_(self.config.title))
        self.window.setContentView_(self.webview)
        self.window.center()
        
        if self.config.always_on_top:
            self.window.setLevel_(3)
        
        self.state = WebViewState.CREATED
        
        if self.config.url:
            await self.load_url(self.config.url)
        elif self.config.html:
            await self.load_html(self.config.html)
        
        await self.emit_event(WebViewEventType.READY)
        logger.info(f"macOS WebView created successfully: {self.webview_id}")
    
    def _configure_security(self) -> None:
        """Configure WebView security settings."""
        security_config = self._apply_security_config()
        
        preferences = WKPreferences.alloc().init()
        preferences.setJavaScriptEnabled_(security_config['enable_javascript'])
        preferences.setPlugInsEnabled_(security_config['enable_plugins'])
        
        if security_config['enable_dev_tools']:
            preferences.setValue_forKey_(True, "developerExtrasEnabled")
        
        self.configuration.setPreferences_(preferences)
        
        if self.config.security_policy == SecurityPolicy.STRICT:
            data_store = WKWebsiteDataStore.nonPersistentDataStore()
            self.configuration.setWebsiteDataStore_(data_store)
        
        process_pool = WKProcessPool.alloc().init()
        self.configuration.setProcessPool_(process_pool)
    
    def _setup_ipc_bridge(self) -> None:
        """Set up IPC bridge for PyElectron API."""
        content_controller = self.configuration.userContentController()
        
        self.script_handler = PyElectronScriptMessageHandler.alloc().initWithWebView_(self)
        content_controller.addScriptMessageHandler_name_(
            self.script_handler, 
            NSString.stringWithString_(self.config.ipc_namespace)
        )
        
        api_script = self._generate_api_script()
        user_script = WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
            NSString.stringWithString_(api_script),
            WKUserScriptInjectionTime.WKUserScriptInjectionTimeAtDocumentStart,
            True
        )
        content_controller.addUserScript_(user_script)
    
    def _generate_api_script(self) -> str:
        """Generate JavaScript API for PyElectron integration."""
        namespace = self.config.ipc_namespace
        
        return f"""
        (function() {{
            window.{namespace} = {{
                send: function(method, params) {{
                    window.webkit.messageHandlers.{namespace}.postMessage({{
                        type: 'pyelectron_ipc',
                        method: method,
                        params: params || null,
                        id: Math.random().toString(36).substr(2, 9)
                    }});
                }},
                log: function(message) {{
                    window.webkit.messageHandlers.{namespace}.postMessage({{
                        type: 'console_log',
                        message: message
                    }});
                }},
                platform: 'darwin',
                version: '{self.webview_id}'
            }};
            
            {self._get_custom_css_script()}
            
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
    
    async def _handle_ipc_message(self, message: dict) -> None:
        """Handle IPC message from JavaScript."""
        try:
            method = message.get('method')
            params = message.get('params')
            
            await self.emit_event(WebViewEventType.CONSOLE_MESSAGE, {
                'type': 'ipc',
                'method': method,
                'params': params
            })
            
        except Exception as e:
            logger.error(f"Error handling IPC message: {e}")
    
    @handle_exception
    async def load_url(self, url: str) -> None:
        """Load a URL in the WebView."""
        if not self.webview:
            raise WebViewError("WebView not created")
        
        if not self._validate_url(url):
            raise WebViewError(f"URL not allowed by security policy: {url}")
        
        logger.debug(f"Loading URL: {url}")
        self.state = WebViewState.LOADING
        
        ns_url = NSURL.URLWithString_(NSString.stringWithString_(url))
        request = NSURLRequest.requestWithURL_(ns_url)
        self.webview.loadRequest_(request)
    
    @handle_exception
    async def load_html(self, html: str, base_url: Optional[str] = None) -> None:
        """Load HTML content in the WebView."""
        if not self.webview:
            raise WebViewError("WebView not created")
        
        logger.debug("Loading HTML content")
        self.state = WebViewState.LOADING
        
        ns_html = NSString.stringWithString_(html)
        
        if base_url:
            ns_base_url = NSURL.URLWithString_(NSString.stringWithString_(base_url))
            self.webview.loadHTMLString_baseURL_(ns_html, ns_base_url)
        else:
            self.webview.loadHTMLString_baseURL_(ns_html, None)
    
    @handle_exception
    async def execute_javascript(self, script: str) -> Any:
        """Execute JavaScript in the WebView and return result."""
        if not self.webview:
            raise WebViewError("WebView not created")
        
        logger.debug(f"Executing JavaScript: {script[:100]}...")
        
        future = asyncio.get_event_loop().create_future()
        
        def completion_handler(result, error):
            if error:
                future.set_exception(WebViewError(f"JavaScript error: {error.localizedDescription()}"))
            else:
                future.set_result(result)
        
        ns_script = NSString.stringWithString_(script)
        self.webview.evaluateJavaScript_completionHandler_(ns_script, completion_handler)
        
        return await future
    
    @handle_exception
    async def show(self) -> None:
        """Show the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        self.window.makeKeyAndOrderFront_(None)
    
    @handle_exception
    async def hide(self) -> None:
        """Hide the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        self.window.orderOut_(None)
    
    @handle_exception
    async def close(self) -> None:
        """Close the WebView and cleanup resources."""
        logger.info(f"Closing macOS WebView: {self.webview_id}")
        
        self.state = WebViewState.DESTROYED
        
        if self.window:
            self.window.close()
            self.window = None
        
        if self.webview:
            self.webview.setNavigationDelegate_(None)
            self.webview.setUIDelegate_(None)
            
            if self.script_handler:
                content_controller = self.webview.configuration().userContentController()
                content_controller.removeScriptMessageHandlerForName_(
                    NSString.stringWithString_(self.config.ipc_namespace)
                )
            
            self.webview = None
        
        self.navigation_delegate = None
        self.ui_delegate = None
        self.script_handler = None
        self.configuration = None
    
    @handle_exception
    async def resize(self, width: int, height: int) -> None:
        """Resize the WebView window."""
        if not self.window:
            raise WebViewError("Window not created")
        
        frame = self.window.frame()
        frame.size.width = width
        frame.size.height = height
        self.window.setFrame_display_(frame, True)
    
    @handle_exception
    async def get_url(self) -> Optional[str]:
        """Get the current URL."""
        if not self.webview:
            return None
        
        url = self.webview.URL()
        return str(url) if url else None
    
    @handle_exception
    async def get_title(self) -> Optional[str]:
        """Get the current page title."""
        if not self.webview:
            return None
        
        title = self.webview.title()
        return str(title) if title else None
    
    def set_security_policy(self, policy: SecurityPolicy) -> None:
        """Configure security policy for the WebView."""
        self.config.security_policy = policy