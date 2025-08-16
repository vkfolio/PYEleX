"""
Utility modules

This package provides common utilities, error handling,
configuration management, and platform abstractions.
"""

from pyelectron.utils.errors import (
    PyElectronError,
    IPCError,
    WebViewError,
    PermissionError,
    StateError,
)
from pyelectron.utils.logging import get_logger
from pyelectron.utils.config import ConfigManager
from pyelectron.utils.platform import PlatformUtils

__all__ = [
    # Exceptions
    "PyElectronError",
    "IPCError",
    "WebViewError", 
    "PermissionError",
    "StateError",
    
    # Utilities
    "get_logger",
    "ConfigManager",
    "PlatformUtils",
]