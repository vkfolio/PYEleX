"""
PyElectron - A pragmatic Python desktop application framework

PyElectron enables developers to build cross-platform desktop applications
using Python as the backend and modern web technologies for the frontend.
It focuses on simplicity, security, and developer experience.
"""

__version__ = "0.1.0-alpha.1"
__author__ = "PyElectron Team"
__email__ = "team@pyelectron.dev"
__license__ = "MIT"

# Core imports for easy access
from pyelectron.core.app import PyElectronApp
from pyelectron.core.window import WindowConfig, WindowManager
from pyelectron.core.process import ProcessManager

# IPC imports
from pyelectron.ipc.jsonrpc import JSONRPCHandler
from pyelectron.ipc.shared_memory import SharedDataManager

# Security imports
from pyelectron.security.permissions import Permission, PermissionManager

# State management
from pyelectron.state.manager import StateManager

# Utility imports
from pyelectron.utils.errors import (
    PyElectronError,
    IPCError,
    WebViewError,
    PermissionError,
    StateError,
)

# Version info
VERSION_INFO = tuple(int(part) for part in __version__.split('.') if part.isdigit())

__all__ = [
    # Core classes
    "PyElectronApp",
    "WindowConfig", 
    "WindowManager",
    "ProcessManager",
    
    # IPC
    "JSONRPCHandler",
    "SharedDataManager",
    
    # Security
    "Permission",
    "PermissionManager",
    
    # State
    "StateManager",
    
    # Exceptions
    "PyElectronError",
    "IPCError", 
    "WebViewError",
    "PermissionError",
    "StateError",
    
    # Version info
    "__version__",
    "VERSION_INFO",
]

# Runtime platform detection and validation
import sys
import platform as platform_module

def _validate_python_version():
    """Validate Python version compatibility"""
    if sys.version_info < (3, 8):
        raise RuntimeError(
            f"PyElectron requires Python 3.8 or higher. "
            f"Current version: {sys.version}"
        )

def _detect_platform():
    """Detect current platform and WebView availability"""
    system = platform_module.system()
    
    platform_info = {
        'system': system,
        'version': platform_module.version(),
        'architecture': platform_module.architecture()[0],
        'webview_available': False,
        'webview_backend': None,
    }
    
    # Check WebView availability per platform
    if system == 'Windows':
        try:
            import webview
            platform_info['webview_available'] = True
            platform_info['webview_backend'] = 'webview2'
        except ImportError:
            platform_info['webview_error'] = (
                "WebView2 not available. Please install: pip install pywebview[cef]"
            )
    
    elif system == 'Darwin':  # macOS
        try:
            import objc
            from WebKit import WKWebView
            platform_info['webview_available'] = True
            platform_info['webview_backend'] = 'wkwebview'
        except ImportError:
            platform_info['webview_error'] = (
                "WKWebView not available. Please install: pip install pyobjc-framework-WebKit"
            )
    
    elif system == 'Linux':
        try:
            import gi
            gi.require_version('WebKit2', '4.0')
            from gi.repository import WebKit2
            platform_info['webview_available'] = True
            platform_info['webview_backend'] = 'webkit2gtk'
        except (ImportError, ValueError):
            platform_info['webview_error'] = (
                "WebKit2GTK not available. Please install:\n"
                "Ubuntu/Debian: sudo apt install python3-gi webkit2gtk-4.0\n"
                "Fedora: sudo dnf install python3-gobject webkit2gtk4\n"
                "Arch: sudo pacman -S python-gobject webkit2gtk"
            )
    
    return platform_info

# Initialize platform detection
try:
    _validate_python_version()
    PLATFORM_INFO = _detect_platform()
except Exception as e:
    # Store error for later reporting
    PLATFORM_INFO = {
        'error': str(e),
        'system': platform_module.system(),
        'webview_available': False,
    }

def get_platform_info():
    """Get detailed platform information including WebView availability"""
    return PLATFORM_INFO.copy()

def check_webview_availability():
    """Check if WebView is available on current platform"""
    if 'error' in PLATFORM_INFO:
        return False, PLATFORM_INFO['error']
    
    if not PLATFORM_INFO['webview_available']:
        error_msg = PLATFORM_INFO.get('webview_error', 'WebView not available')
        return False, error_msg
    
    return True, f"WebView available: {PLATFORM_INFO['webview_backend']}"

# Convenience function for quick app creation
def create_app(name: str = "PyElectronApp", **kwargs) -> "PyElectronApp":
    """
    Create a new PyElectron application with default configuration.
    
    Args:
        name: Application name
        **kwargs: Additional configuration options
        
    Returns:
        PyElectronApp instance
        
    Example:
        >>> app = pyelectron.create_app("MyApp")
        >>> app.run()
    """
    return PyElectronApp(name=name, **kwargs)