"""
PyElectron WebView Package

This package provides cross-platform WebView functionality for PyElectron
desktop applications with native backends for Windows, macOS, and Linux.
"""

# Import platform-specific backends to register them
try:
    from . import macos
except ImportError:
    pass

try:
    from . import windows
except ImportError:
    pass

try:
    from . import linux
except ImportError:
    pass

# Core WebView components
from .base import (
    BaseWebView,
    WebViewConfig,
    WebViewInfo,
    WebViewEvent,
    WebViewEventType,
    WebViewState,
    SecurityPolicy,
    WebViewFactory,
    create_default_config,
)

from .manager import (
    WebViewManager,
    WebViewService,
    create_webview_manager,
)

from .security import (
    WebViewSecurityConfig,
    SecurityPolicyManager,
    URLValidator,
    ContentSecurityPolicy,
)

from .policies import (
    WebViewSecurityPolicy,
    ResourceType,
    ActionType,
    PolicyTemplate,
    create_security_policy,
)

from .events import (
    EventBus,
    EventPriority,
    WebViewEventManager,
    create_event_manager,
    get_global_event_bus,
)

from .ipc_bridge import (
    WebViewIPCBridge,
    create_ipc_bridge,
)

__all__ = [
    # Base classes and interfaces
    'BaseWebView',
    'WebViewConfig', 
    'WebViewInfo',
    'WebViewEvent',
    'WebViewEventType',
    'WebViewState',
    'SecurityPolicy',
    'WebViewFactory',
    'create_default_config',
    
    # Management classes
    'WebViewManager',
    'WebViewService',
    'create_webview_manager',
    
    # Security classes
    'WebViewSecurityConfig',
    'SecurityPolicyManager',
    'URLValidator',
    'ContentSecurityPolicy',
    'WebViewSecurityPolicy',
    'ResourceType',
    'ActionType',
    'PolicyTemplate',
    'create_security_policy',
    
    # Event system
    'EventBus',
    'EventPriority',
    'WebViewEventManager',
    'create_event_manager',
    'get_global_event_bus',
    
    # IPC integration
    'WebViewIPCBridge',
    'create_ipc_bridge',
]