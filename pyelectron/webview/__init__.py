"""
WebView integration modules

This package provides cross-platform WebView integration using
native platform WebView components for optimal performance.
"""

from pyelectron.webview.native import NativeWebView
from pyelectron.webview.manager import WebViewManager

__all__ = [
    "NativeWebView",
    "WebViewManager",
]