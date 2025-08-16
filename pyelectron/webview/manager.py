"""
PyElectron WebView Manager

This module provides high-level WebView management, including lifecycle
management, event coordination, and integration with the process system.
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Callable, Any

from .base import (
    BaseWebView, WebViewConfig, WebViewFactory, WebViewInfo, 
    WebViewEvent, WebViewEventType, SecurityPolicy, create_default_config
)
from pyelectron.utils.errors import WebViewError, handle_exception
from pyelectron.utils.logging import get_logger
from pyelectron.utils.platform import PlatformUtils

logger = get_logger(__name__)


class WebViewManager:
    """
    High-level WebView manager for PyElectron applications.
    
    Manages the lifecycle of WebView instances, coordinates events,
    and provides integration with the process and IPC systems.
    """
    
    def __init__(self):
        self.webviews: Dict[str, BaseWebView] = {}
        self.event_handlers: Dict[WebViewEventType, List[Callable]] = {}
        self.is_initialized = False
        self.platform_utils = PlatformUtils()
        
        # Initialize event handlers
        for event_type in WebViewEventType:
            self.event_handlers[event_type] = []
        
        logger.debug("WebViewManager initialized")
    
    @handle_exception
    async def initialize(self):
        """Initialize the WebView manager."""
        if self.is_initialized:
            return
        
        logger.info("Initializing WebViewManager")
        
        # Check platform WebView availability
        webview_available, message = self.platform_utils.check_webview_availability()
        if not webview_available:
            logger.warning(f"WebView not available: {message}")
            # Continue initialization but log warning
        
        self.is_initialized = True
        logger.info("WebViewManager initialized successfully")
    
    @handle_exception
    async def create_webview(self, config: Optional[WebViewConfig] = None, 
                           webview_id: Optional[str] = None) -> str:
        """
        Create a new WebView instance.
        
        Args:
            config: WebView configuration (uses defaults if None)
            webview_id: Custom WebView ID (auto-generated if None)
            
        Returns:
            str: WebView ID
        """
        if not self.is_initialized:
            await self.initialize()
        
        if webview_id is None:
            webview_id = str(uuid.uuid4())
        
        if webview_id in self.webviews:
            raise WebViewError(f"WebView already exists: {webview_id}")
        
        if config is None:
            config = create_default_config()
        
        logger.info(f"Creating WebView: {webview_id}")
        
        try:
            # Create platform-specific WebView
            webview = WebViewFactory.create_webview(webview_id, config)
            
            # Set up global event handling
            self._setup_webview_events(webview)
            
            # Create the native WebView
            await webview.create()
            
            # Store WebView instance
            self.webviews[webview_id] = webview
            
            logger.info(f"WebView created successfully: {webview_id}")
            return webview_id
            
        except Exception as e:
            logger.error(f"Failed to create WebView {webview_id}: {e}")
            raise WebViewError(f"Failed to create WebView: {str(e)}") from e
    
    def _setup_webview_events(self, webview: BaseWebView):
        """Set up event forwarding for a WebView."""
        for event_type in WebViewEventType:
            webview.add_event_handler(event_type, self._forward_event)
    
    async def _forward_event(self, event: WebViewEvent):
        """Forward WebView event to global handlers."""
        handlers = self.event_handlers.get(event.event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in WebView event handler: {e}")
    
    @handle_exception
    async def show_webview(self, webview_id: str):
        """Show a WebView window."""
        webview = self._get_webview(webview_id)
        await webview.show()
        logger.debug(f"WebView shown: {webview_id}")
    
    @handle_exception
    async def hide_webview(self, webview_id: str):
        """Hide a WebView window."""
        webview = self._get_webview(webview_id)
        await webview.hide()
        logger.debug(f"WebView hidden: {webview_id}")
    
    @handle_exception
    async def close_webview(self, webview_id: str):
        """Close and cleanup a WebView."""
        if webview_id not in self.webviews:
            logger.warning(f"Attempted to close non-existent WebView: {webview_id}")
            return
        
        logger.info(f"Closing WebView: {webview_id}")
        
        webview = self.webviews[webview_id]
        
        try:
            await webview.close()
        except Exception as e:
            logger.error(f"Error closing WebView {webview_id}: {e}")
        finally:
            # Remove from our tracking
            del self.webviews[webview_id]
            logger.info(f"WebView closed and removed: {webview_id}")
    
    @handle_exception
    async def load_url(self, webview_id: str, url: str):
        """Load a URL in a WebView."""
        webview = self._get_webview(webview_id)
        await webview.load_url(url)
        logger.debug(f"URL loaded in WebView {webview_id}: {url}")
    
    @handle_exception
    async def load_html(self, webview_id: str, html: str, base_url: Optional[str] = None):
        """Load HTML content in a WebView."""
        webview = self._get_webview(webview_id)
        await webview.load_html(html, base_url)
        logger.debug(f"HTML loaded in WebView {webview_id}")
    
    @handle_exception
    async def execute_javascript(self, webview_id: str, script: str) -> Any:
        """Execute JavaScript in a WebView."""
        webview = self._get_webview(webview_id)
        result = await webview.execute_javascript(script)
        logger.debug(f"JavaScript executed in WebView {webview_id}")
        return result
    
    @handle_exception
    async def resize_webview(self, webview_id: str, width: int, height: int):
        """Resize a WebView window."""
        webview = self._get_webview(webview_id)
        await webview.resize(width, height)
        logger.debug(f"WebView {webview_id} resized to {width}x{height}")
    
    def get_webview_info(self, webview_id: str) -> Optional[WebViewInfo]:
        """Get information about a WebView."""
        if webview_id not in self.webviews:
            return None
        
        webview = self.webviews[webview_id]
        return webview.get_info()
    
    def list_webviews(self) -> Dict[str, WebViewInfo]:
        """Get information about all WebViews."""
        return {
            webview_id: webview.get_info()
            for webview_id, webview in self.webviews.items()
        }
    
    def get_webview_count(self) -> int:
        """Get the number of active WebViews."""
        return len(self.webviews)
    
    @handle_exception
    async def get_webview_url(self, webview_id: str) -> Optional[str]:
        """Get the current URL of a WebView."""
        webview = self._get_webview(webview_id)
        return await webview.get_url()
    
    @handle_exception
    async def get_webview_title(self, webview_id: str) -> Optional[str]:
        """Get the current title of a WebView."""
        webview = self._get_webview(webview_id)
        return await webview.get_title()
    
    def set_security_policy(self, webview_id: str, policy: SecurityPolicy):
        """Set security policy for a WebView."""
        webview = self._get_webview(webview_id)
        webview.set_security_policy(policy)
        logger.debug(f"Security policy set for WebView {webview_id}: {policy.value}")
    
    def add_event_handler(self, event_type: WebViewEventType, handler: Callable):
        """Add global event handler for WebView events."""
        self.event_handlers[event_type].append(handler)
        logger.debug(f"Added global event handler for {event_type.value}")
    
    def remove_event_handler(self, event_type: WebViewEventType, handler: Callable):
        """Remove global event handler for WebView events."""
        try:
            self.event_handlers[event_type].remove(handler)
            logger.debug(f"Removed global event handler for {event_type.value}")
        except ValueError:
            logger.warning(f"Handler not found for {event_type.value}")
    
    async def close_all_webviews(self):
        """Close all WebViews."""
        logger.info("Closing all WebViews")
        
        webview_ids = list(self.webviews.keys())
        
        # Close all WebViews concurrently
        close_tasks = [
            self.close_webview(webview_id) 
            for webview_id in webview_ids
        ]
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        logger.info("All WebViews closed")
    
    async def cleanup(self):
        """Cleanup WebView manager."""
        logger.info("Cleaning up WebViewManager")
        
        # Close all WebViews
        await self.close_all_webviews()
        
        # Clear event handlers
        for event_type in self.event_handlers:
            self.event_handlers[event_type].clear()
        
        self.is_initialized = False
        logger.info("WebViewManager cleanup completed")
    
    def _get_webview(self, webview_id: str) -> BaseWebView:
        """Get WebView instance or raise error."""
        if webview_id not in self.webviews:
            raise WebViewError(f"WebView not found: {webview_id}")
        
        return self.webviews[webview_id]
    
    def get_platform_info(self) -> Dict[str, Any]:
        """Get platform WebView information."""
        return self.platform_utils.get_platform_info()
    
    def get_available_backends(self) -> List[str]:
        """Get list of available WebView backends."""
        return WebViewFactory.get_available_backends()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()


class WebViewService:
    """
    Service class for exposing WebView functionality via IPC.
    
    This allows other processes to create and manage WebViews
    through the IPC system.
    """
    
    def __init__(self, webview_manager: WebViewManager):
        self.webview_manager = webview_manager
        self.service_name = "webview"
        
        logger.debug("WebViewService initialized")
    
    async def create_window(self, config: Optional[Dict[str, Any]] = None) -> str:
        """Create a new WebView window via IPC."""
        if config:
            # Convert dict to WebViewConfig
            webview_config = WebViewConfig(**config)
        else:
            webview_config = None
        
        webview_id = await self.webview_manager.create_webview(webview_config)
        return webview_id
    
    async def load_url(self, webview_id: str, url: str) -> bool:
        """Load URL in WebView via IPC."""
        try:
            await self.webview_manager.load_url(webview_id, url)
            return True
        except Exception as e:
            logger.error(f"Error loading URL via IPC: {e}")
            return False
    
    async def execute_js(self, webview_id: str, script: str) -> Any:
        """Execute JavaScript via IPC."""
        try:
            return await self.webview_manager.execute_javascript(webview_id, script)
        except Exception as e:
            logger.error(f"Error executing JavaScript via IPC: {e}")
            return None
    
    async def close_window(self, webview_id: str) -> bool:
        """Close WebView window via IPC."""
        try:
            await self.webview_manager.close_webview(webview_id)
            return True
        except Exception as e:
            logger.error(f"Error closing WebView via IPC: {e}")
            return False
    
    async def get_window_info(self, webview_id: str) -> Optional[Dict[str, Any]]:
        """Get WebView information via IPC."""
        info = self.webview_manager.get_webview_info(webview_id)
        if info:
            # Convert to dict for IPC serialization
            return {
                'webview_id': info.webview_id,
                'state': info.state.value,
                'current_url': info.current_url,
                'title': info.title,
                'backend': info.backend,
                'created_at': info.created_at
            }
        return None
    
    async def list_windows(self) -> Dict[str, Dict[str, Any]]:
        """List all WebViews via IPC."""
        webviews = self.webview_manager.list_webviews()
        
        # Convert to dict for IPC serialization
        return {
            webview_id: {
                'webview_id': info.webview_id,
                'state': info.state.value,
                'current_url': info.current_url,
                'title': info.title,
                'backend': info.backend,
                'created_at': info.created_at
            }
            for webview_id, info in webviews.items()
        }


def create_webview_manager() -> WebViewManager:
    """Create WebView manager with default configuration."""
    return WebViewManager()