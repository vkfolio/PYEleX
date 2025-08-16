"""
PyElectron WebView Base Classes

This module provides the base interface and common functionality
for platform-specific WebView implementations.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from pyelectron.utils.errors import WebViewError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class WebViewState(Enum):
    """WebView lifecycle states."""
    CREATED = "created"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    DESTROYED = "destroyed"


class SecurityPolicy(Enum):
    """WebView security policies."""
    STRICT = "strict"          # Maximum security, minimal web features
    BALANCED = "balanced"      # Good security with common web features
    PERMISSIVE = "permissive"  # Minimal security, maximum compatibility


@dataclass
class WebViewConfig:
    """WebView configuration options."""
    
    # Window properties
    width: int = 1024
    height: int = 768
    title: str = "PyElectron App"
    resizable: bool = True
    minimizable: bool = True
    maximizable: bool = True
    closable: bool = True
    always_on_top: bool = False
    fullscreen: bool = False
    
    # Content properties
    url: Optional[str] = None
    html: Optional[str] = None
    
    # Security properties
    security_policy: SecurityPolicy = SecurityPolicy.BALANCED
    enable_dev_tools: bool = False
    enable_context_menu: bool = True
    enable_javascript: bool = True
    enable_plugins: bool = False
    
    # Navigation restrictions
    allowed_hosts: Optional[List[str]] = None
    blocked_hosts: List[str] = field(default_factory=list)
    allow_external_navigation: bool = False
    
    # Custom properties
    custom_css: Optional[str] = None
    custom_js: Optional[str] = None
    user_agent: Optional[str] = None
    
    # PyElectron integration
    enable_pyelectron_api: bool = True
    ipc_namespace: str = "pyelectron"


@dataclass
class WebViewInfo:
    """Information about a WebView instance."""
    
    webview_id: str
    config: WebViewConfig
    state: WebViewState
    current_url: Optional[str] = None
    title: Optional[str] = None
    created_at: float = 0.0
    backend: str = "unknown"
    process_id: Optional[int] = None


class WebViewEventType(Enum):
    """WebView event types."""
    READY = "ready"
    NAVIGATION_START = "navigation_start"
    NAVIGATION_COMPLETE = "navigation_complete"
    NAVIGATION_ERROR = "navigation_error"
    TITLE_CHANGED = "title_changed"
    CLOSE_REQUESTED = "close_requested"
    CONSOLE_MESSAGE = "console_message"
    ALERT = "alert"
    CONFIRM = "confirm"
    PROMPT = "prompt"


@dataclass
class WebViewEvent:
    """WebView event data."""
    
    event_type: WebViewEventType
    webview_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class BaseWebView(ABC):
    """
    Abstract base class for platform-specific WebView implementations.
    
    This defines the common interface that all WebView backends must implement,
    ensuring consistent behavior across Windows, macOS, and Linux.
    """
    
    def __init__(self, webview_id: str, config: WebViewConfig):
        self.webview_id = webview_id
        self.config = config
        self.state = WebViewState.CREATED
        self.event_handlers: Dict[WebViewEventType, List[Callable]] = {}
        self.native_webview = None
        self.ipc_bridge = None
        
        # Initialize event handlers
        for event_type in WebViewEventType:
            self.event_handlers[event_type] = []
        
        logger.debug(f"WebView {webview_id} created with backend: {self.__class__.__name__}")
    
    @abstractmethod
    async def create(self) -> None:
        """Create the native WebView instance."""
        pass
    
    @abstractmethod
    async def load_url(self, url: str) -> None:
        """Load a URL in the WebView."""
        pass
    
    @abstractmethod
    async def load_html(self, html: str, base_url: Optional[str] = None) -> None:
        """Load HTML content in the WebView."""
        pass
    
    @abstractmethod
    async def execute_javascript(self, script: str) -> Any:
        """Execute JavaScript in the WebView and return result."""
        pass
    
    @abstractmethod
    async def show(self) -> None:
        """Show the WebView window."""
        pass
    
    @abstractmethod
    async def hide(self) -> None:
        """Hide the WebView window."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the WebView and cleanup resources."""
        pass
    
    @abstractmethod
    async def resize(self, width: int, height: int) -> None:
        """Resize the WebView window."""
        pass
    
    @abstractmethod
    async def get_url(self) -> Optional[str]:
        """Get the current URL."""
        pass
    
    @abstractmethod
    async def get_title(self) -> Optional[str]:
        """Get the current page title."""
        pass
    
    @abstractmethod
    def set_security_policy(self, policy: SecurityPolicy) -> None:
        """Configure security policy for the WebView."""
        pass
    
    def add_event_handler(self, event_type: WebViewEventType, handler: Callable) -> None:
        """Add event handler for WebView events."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        
        self.event_handlers[event_type].append(handler)
        logger.debug(f"Added event handler for {event_type.value} on WebView {self.webview_id}")
    
    def remove_event_handler(self, event_type: WebViewEventType, handler: Callable) -> None:
        """Remove event handler for WebView events."""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type].remove(handler)
                logger.debug(f"Removed event handler for {event_type.value} on WebView {self.webview_id}")
            except ValueError:
                logger.warning(f"Handler not found for {event_type.value} on WebView {self.webview_id}")
    
    async def emit_event(self, event_type: WebViewEventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit event to all registered handlers."""
        event = WebViewEvent(
            event_type=event_type,
            webview_id=self.webview_id,
            data=data or {},
            timestamp=asyncio.get_event_loop().time()
        )
        
        handlers = self.event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type.value}: {e}")
    
    def get_info(self) -> WebViewInfo:
        """Get WebView information."""
        return WebViewInfo(
            webview_id=self.webview_id,
            config=self.config,
            state=self.state,
            current_url=None,  # Will be implemented by subclasses
            title=None,        # Will be implemented by subclasses
            created_at=asyncio.get_event_loop().time(),
            backend=self.__class__.__name__
        )
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL against security policies."""
        if not url:
            return False
        
        # Check allowed hosts
        if self.config.allowed_hosts:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname
            
            if hostname not in self.config.allowed_hosts:
                logger.warning(f"URL blocked by allowed hosts policy: {url}")
                return False
        
        # Check blocked hosts
        if self.config.blocked_hosts:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname
            
            if hostname in self.config.blocked_hosts:
                logger.warning(f"URL blocked by blocked hosts policy: {url}")
                return False
        
        return True
    
    def _apply_security_config(self) -> Dict[str, Any]:
        """Generate security configuration based on policy."""
        policy = self.config.security_policy
        
        if policy == SecurityPolicy.STRICT:
            return {
                'enable_javascript': False,
                'enable_plugins': False,
                'enable_local_storage': False,
                'enable_cookies': False,
                'enable_cache': False,
                'enable_dev_tools': False,
                'enable_context_menu': False,
            }
        elif policy == SecurityPolicy.BALANCED:
            return {
                'enable_javascript': self.config.enable_javascript,
                'enable_plugins': False,
                'enable_local_storage': True,
                'enable_cookies': True,
                'enable_cache': True,
                'enable_dev_tools': self.config.enable_dev_tools,
                'enable_context_menu': self.config.enable_context_menu,
            }
        else:  # PERMISSIVE
            return {
                'enable_javascript': True,
                'enable_plugins': self.config.enable_plugins,
                'enable_local_storage': True,
                'enable_cookies': True,
                'enable_cache': True,
                'enable_dev_tools': self.config.enable_dev_tools,
                'enable_context_menu': self.config.enable_context_menu,
            }


class WebViewFactory:
    """Factory for creating platform-specific WebView instances."""
    
    _backends: Dict[str, type] = {}
    
    @classmethod
    def register_backend(cls, platform: str, backend_class: type) -> None:
        """Register a WebView backend for a platform."""
        cls._backends[platform] = backend_class
        logger.debug(f"Registered WebView backend for {platform}: {backend_class.__name__}")
    
    @classmethod
    def create_webview(cls, webview_id: str, config: WebViewConfig, 
                      platform: Optional[str] = None) -> BaseWebView:
        """Create a WebView instance for the current or specified platform."""
        if platform is None:
            import platform as platform_module
            platform = platform_module.system()
        
        backend_class = cls._backends.get(platform)
        if not backend_class:
            raise WebViewError(f"No WebView backend registered for platform: {platform}")
        
        return backend_class(webview_id, config)
    
    @classmethod
    def get_available_backends(cls) -> List[str]:
        """Get list of available WebView backends."""
        return list(cls._backends.keys())


def create_default_config(**kwargs) -> WebViewConfig:
    """Create WebView config with secure defaults."""
    return WebViewConfig(
        security_policy=SecurityPolicy.BALANCED,
        enable_dev_tools=False,
        enable_plugins=False,
        allow_external_navigation=False,
        **kwargs
    )