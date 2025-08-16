"""
PyElectron exception classes

This module defines all custom exceptions used throughout PyElectron,
providing clear error messages and proper exception hierarchy.
"""

from typing import Optional, Any


class PyElectronError(Exception):
    """Base exception for all PyElectron errors"""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class IPCError(PyElectronError):
    """Errors related to inter-process communication"""
    pass


class WebViewError(PyElectronError):
    """Errors related to WebView operations"""
    pass


class PermissionError(PyElectronError):
    """Errors related to permission management"""
    pass


class StateError(PyElectronError):
    """Errors related to state management"""
    pass


class ProcessError(PyElectronError):
    """Errors related to process management"""
    pass


class ConfigError(PyElectronError):
    """Errors related to configuration management"""
    pass


class ValidationError(PyElectronError):
    """Errors related to input validation"""
    pass


class PlatformError(PyElectronError):
    """Errors related to platform compatibility"""
    pass


class RPCError(PyElectronError):
    """Errors related to JSON-RPC communication"""
    
    def __init__(self, message: str, code: int = -32603, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data
    
    def to_dict(self) -> dict:
        """Convert to JSON-RPC error format."""
        error_dict = {
            'code': self.code,
            'message': self.message
        }
        if self.data is not None:
            error_dict['data'] = self.data
        return error_dict


class SecurityError(PyElectronError):
    """Errors related to security violations"""
    pass


class TransportError(IPCError):
    """Errors related to IPC transport layer"""
    pass


def handle_exception(func):
    """
    Decorator to handle exceptions and convert them to PyElectron exceptions
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PyElectronError:
            # Re-raise PyElectron exceptions as-is
            raise
        except Exception as e:
            # Convert other exceptions to PyElectronError
            raise PyElectronError(
                f"Unexpected error in {func.__name__}: {str(e)}",
                details={'original_exception': type(e).__name__}
            ) from e
    return wrapper


async def handle_async_exception(func):
    """
    Async decorator to handle exceptions and convert them to PyElectron exceptions
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except PyElectronError:
            # Re-raise PyElectron exceptions as-is
            raise
        except Exception as e:
            # Convert other exceptions to PyElectronError
            raise PyElectronError(
                f"Unexpected error in {func.__name__}: {str(e)}",
                details={'original_exception': type(e).__name__}
            ) from e
    return wrapper