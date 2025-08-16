"""
PyElectron WebView IPC Bridge

This module provides integration between WebView instances and the PyElectron
IPC system, enabling secure communication between web content and Python backend.
"""

import asyncio
import json
import uuid
from typing import Any, Callable, Dict, Optional

from .base import BaseWebView, WebViewEventType
from pyelectron.ipc import IPCManager, ServiceRegistry, MessageRouter, rpc_method
from pyelectron.utils.errors import IPCError, SecurityError
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class WebViewIPCBridge:
    """
    Bridge between WebView and IPC system.
    
    Handles secure communication between web content (JavaScript) and
    Python backend through the PyElectron IPC system.
    """
    
    def __init__(self, webview: BaseWebView, ipc_manager: Optional[IPCManager] = None):
        self.webview = webview
        self.webview_id = webview.webview_id
        self.ipc_manager = ipc_manager
        self.namespace = webview.config.ipc_namespace
        
        # Message handling
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.request_timeout = 30.0
        
        # Service registry for WebView-specific methods
        self.service_registry = ServiceRegistry()
        self.message_router = MessageRouter(self.service_registry)
        
        # Register built-in WebView API
        self._register_builtin_api()
        
        # Set up WebView event handling
        self._setup_webview_events()
        
        logger.debug(f"WebView IPC Bridge initialized for {self.webview_id}")
    
    def _register_builtin_api(self):
        """Register built-in WebView API methods."""
        self.service_registry.register_service("webview", WebViewAPI(self.webview))
        self.service_registry.register_service("system", SystemAPI())
        
        logger.debug("Built-in WebView API registered")
    
    def _setup_webview_events(self):
        """Set up event handling for WebView."""
        # Listen for console messages that contain IPC data
        self.webview.add_event_handler(WebViewEventType.CONSOLE_MESSAGE, self._handle_console_message)
        
        # Listen for navigation events to inject IPC bridge
        self.webview.add_event_handler(WebViewEventType.NAVIGATION_COMPLETE, self._on_navigation_complete)
    
    async def _handle_console_message(self, event):
        """Handle console messages from WebView."""
        data = event.data
        
        # Check if this is an IPC message
        if isinstance(data, dict) and data.get('type') == 'pyelectron_ipc':
            await self._handle_ipc_message(data)
    
    async def _handle_ipc_message(self, message: Dict[str, Any]):
        """Handle IPC message from JavaScript."""
        try:
            message_type = message.get('message_type', 'request')
            
            if message_type == 'request':
                await self._handle_ipc_request(message)
            elif message_type == 'response':
                await self._handle_ipc_response(message)
            elif message_type == 'notification':
                await self._handle_ipc_notification(message)
            else:
                logger.warning(f"Unknown IPC message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling IPC message: {e}")
    
    async def _handle_ipc_request(self, message: Dict[str, Any]):
        """Handle IPC request from JavaScript."""
        request_id = message.get('id')
        method = message.get('method')
        params = message.get('params')
        
        if not method:
            await self._send_error_response(request_id, "Missing method")
            return
        
        try:
            # Route message through the message router
            result = await self.message_router.route_message(
                method, 
                params,
                context={'webview_id': self.webview_id}
            )
            
            # Send success response
            await self._send_response(request_id, result)
            
        except Exception as e:
            logger.error(f"Error processing IPC request {method}: {e}")
            await self._send_error_response(request_id, str(e))
    
    async def _handle_ipc_response(self, message: Dict[str, Any]):
        """Handle IPC response from JavaScript."""
        request_id = message.get('id')
        
        if request_id not in self.pending_requests:
            logger.warning(f"Received response for unknown request: {request_id}")
            return
        
        future = self.pending_requests.pop(request_id)
        
        if 'error' in message:
            error_msg = message['error']
            future.set_exception(IPCError(f"JavaScript error: {error_msg}"))
        else:
            result = message.get('result')
            future.set_result(result)
    
    async def _handle_ipc_notification(self, message: Dict[str, Any]):
        """Handle IPC notification from JavaScript."""
        method = message.get('method')
        params = message.get('params')
        
        if not method:
            logger.warning("Notification missing method")
            return
        
        try:
            # Route notification through the message router
            await self.message_router.route_message(
                method,
                params,
                context={'webview_id': self.webview_id, 'notification': True}
            )
            
        except Exception as e:
            logger.error(f"Error processing IPC notification {method}: {e}")
    
    async def _send_response(self, request_id: str, result: Any):
        """Send successful response to JavaScript."""
        response = {
            'type': 'pyelectron_ipc_response',
            'id': request_id,
            'result': result
        }
        
        script = f"""
        if (window.{self.namespace} && window.{self.namespace}._handleResponse) {{
            window.{self.namespace}._handleResponse({json.dumps(response)});
        }}
        """
        
        try:
            await self.webview.execute_javascript(script)
        except Exception as e:
            logger.error(f"Error sending IPC response: {e}")
    
    async def _send_error_response(self, request_id: str, error_message: str):
        """Send error response to JavaScript."""
        response = {
            'type': 'pyelectron_ipc_response',
            'id': request_id,
            'error': error_message
        }
        
        script = f"""
        if (window.{self.namespace} && window.{self.namespace}._handleResponse) {{
            window.{self.namespace}._handleResponse({json.dumps(response)});
        }}
        """
        
        try:
            await self.webview.execute_javascript(script)
        except Exception as e:
            logger.error(f"Error sending IPC error response: {e}")
    
    async def _on_navigation_complete(self, event):
        """Handle navigation complete to inject IPC bridge."""
        try:
            # Inject enhanced IPC bridge script
            bridge_script = self._generate_ipc_bridge_script()
            await self.webview.execute_javascript(bridge_script)
            
            logger.debug(f"IPC bridge injected for WebView {self.webview_id}")
            
        except Exception as e:
            logger.error(f"Error injecting IPC bridge: {e}")
    
    def _generate_ipc_bridge_script(self) -> str:
        """Generate JavaScript IPC bridge for injection."""
        namespace = self.namespace
        
        return f"""
        (function() {{
            if (window.{namespace}) {{
                return; // Already initialized
            }}
            
            // Create enhanced PyElectron API
            window.{namespace} = {{
                // Send request and wait for response
                invoke: function(method, params) {{
                    return new Promise(function(resolve, reject) {{
                        var id = Math.random().toString(36).substr(2, 9);
                        
                        // Store promise handlers
                        if (!window.{namespace}._pendingRequests) {{
                            window.{namespace}._pendingRequests = {{}};
                        }}
                        window.{namespace}._pendingRequests[id] = {{ resolve: resolve, reject: reject }};
                        
                        // Send message
                        var message = {{
                            type: 'pyelectron_ipc',
                            message_type: 'request',
                            id: id,
                            method: method,
                            params: params || null
                        }};
                        
                        console.log(JSON.stringify(message));
                    }});
                }},
                
                // Send notification (no response expected)
                notify: function(method, params) {{
                    var message = {{
                        type: 'pyelectron_ipc',
                        message_type: 'notification',
                        method: method,
                        params: params || null
                    }};
                    
                    console.log(JSON.stringify(message));
                }},
                
                // Internal response handler
                _handleResponse: function(response) {{
                    if (!window.{namespace}._pendingRequests) {{
                        return;
                    }}
                    
                    var pending = window.{namespace}._pendingRequests[response.id];
                    if (pending) {{
                        delete window.{namespace}._pendingRequests[response.id];
                        
                        if (response.error) {{
                            pending.reject(new Error(response.error));
                        }} else {{
                            pending.resolve(response.result);
                        }}
                    }}
                }},
                
                // Utility methods
                log: function(message) {{
                    window.{namespace}.notify('webview.log', {{ message: message }});
                }},
                
                // Platform info
                platform: '{self.webview.get_info().backend}',
                webviewId: '{self.webview_id}',
                ready: true
            }};
            
            // Initialize pending requests
            window.{namespace}._pendingRequests = {{}};
            
            // Dispatch ready event
            window.dispatchEvent(new CustomEvent('pyelectron:ready', {{
                detail: {{ webviewId: '{self.webview_id}' }}
            }}));
            
            console.log('PyElectron IPC Bridge initialized');
        }})();
        """
    
    async def call_javascript(self, method: str, params: Any = None, timeout: float = None) -> Any:
        """Call JavaScript function from Python."""
        if timeout is None:
            timeout = self.request_timeout
        
        request_id = str(uuid.uuid4())
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future
        
        try:
            # Send request to JavaScript
            request = {
                'type': 'pyelectron_ipc_request',
                'id': request_id,
                'method': method,
                'params': params
            }
            
            script = f"""
            if (window.{self.namespace} && window.{self.namespace}._handleRequest) {{
                window.{self.namespace}._handleRequest({json.dumps(request)});
            }} else {{
                console.error('PyElectron IPC Bridge not ready');
            }}
            """
            
            await self.webview.execute_javascript(script)
            
            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise IPCError(f"JavaScript call timed out: {method}")
        except Exception:
            self.pending_requests.pop(request_id, None)
            raise
    
    def register_service(self, service_name: str, service_obj: Any):
        """Register service for IPC access."""
        self.service_registry.register_service(service_name, service_obj)
        logger.debug(f"Service registered: {service_name}")
    
    def register_method(self, method_name: str, handler: Callable):
        """Register individual method for IPC access."""
        self.service_registry.register_method(method_name, handler)
        logger.debug(f"Method registered: {method_name}")


class WebViewAPI:
    """Built-in WebView API exposed to JavaScript."""
    
    def __init__(self, webview: BaseWebView):
        self.webview = webview
    
    @rpc_method("webview.get_url")
    async def get_url(self) -> Optional[str]:
        """Get current WebView URL."""
        return await self.webview.get_url()
    
    @rpc_method("webview.get_title")
    async def get_title(self) -> Optional[str]:
        """Get current WebView title."""
        return await self.webview.get_title()
    
    @rpc_method("webview.load_url")
    async def load_url(self, url: str) -> bool:
        """Load URL in WebView."""
        try:
            await self.webview.load_url(url)
            return True
        except Exception as e:
            logger.error(f"Error loading URL: {e}")
            return False
    
    @rpc_method("webview.resize")
    async def resize(self, width: int, height: int) -> bool:
        """Resize WebView window."""
        try:
            await self.webview.resize(width, height)
            return True
        except Exception as e:
            logger.error(f"Error resizing WebView: {e}")
            return False
    
    @rpc_method("webview.log")
    async def log(self, message: str):
        """Log message from JavaScript."""
        logger.info(f"JavaScript log [{self.webview.webview_id}]: {message}")


class SystemAPI:
    """System API exposed to JavaScript."""
    
    @rpc_method("system.get_platform")
    def get_platform(self) -> str:
        """Get platform information."""
        import platform
        return platform.system()
    
    @rpc_method("system.get_version")
    def get_version(self) -> str:
        """Get PyElectron version."""
        try:
            import pyelectron
            return pyelectron.__version__
        except:
            return "unknown"
    
    @rpc_method("system.ping")
    def ping(self) -> str:
        """Simple ping for connectivity testing."""
        return "pong"


def create_ipc_bridge(webview: BaseWebView, ipc_manager: Optional[IPCManager] = None) -> WebViewIPCBridge:
    """Create IPC bridge for WebView."""
    return WebViewIPCBridge(webview, ipc_manager)