"""
PyElectron WebView macOS Implementation

This module provides WebView implementation for macOS using WKWebView
through PyObjC bindings.
"""

try:
    import objc
    WEBKIT_AVAILABLE = True
    
    # Import the actual implementation
    from .macos_backend import macOSWebView
    
except ImportError:
    WEBKIT_AVAILABLE = False
    macOSWebView = None

from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)

if not WEBKIT_AVAILABLE:
    logger.warning("WebKit not available on macOS")

# Register the macOS backend if available
if WEBKIT_AVAILABLE:
    from .base import WebViewFactory
    WebViewFactory.register_backend("Darwin", macOSWebView)