"""
Unit tests for PyElectron error handling

Tests the custom exception classes and error handling utilities.
"""

import pytest
from pyelectron.utils.errors import (
    PyElectronError,
    IPCError,
    WebViewError,
    PermissionError,
    StateError,
    ProcessError,
    ConfigError,
    ValidationError,
    PlatformError,
    handle_exception,
    handle_async_exception,
)


class TestPyElectronErrors:
    """Test PyElectron custom exceptions."""
    
    def test_base_exception_with_message_only(self):
        """Test base exception with just a message."""
        error = PyElectronError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}
    
    def test_base_exception_with_details(self):
        """Test base exception with message and details."""
        details = {"component": "test", "code": 123}
        error = PyElectronError("Test error", details=details)
        
        assert "Test error" in str(error)
        assert "Details:" in str(error)
        assert error.message == "Test error"
        assert error.details == details
    
    def test_specific_exception_types(self):
        """Test that specific exception types inherit correctly."""
        exceptions = [
            (IPCError, "IPC error"),
            (WebViewError, "WebView error"),
            (PermissionError, "Permission error"),
            (StateError, "State error"),
            (ProcessError, "Process error"),
            (ConfigError, "Config error"),
            (ValidationError, "Validation error"),
            (PlatformError, "Platform error"),
        ]
        
        for exception_class, message in exceptions:
            error = exception_class(message)
            assert isinstance(error, PyElectronError)
            assert isinstance(error, exception_class)
            assert str(error) == message


class TestErrorHandlingDecorators:
    """Test error handling decorators."""
    
    def test_handle_exception_decorator_passthrough(self):
        """Test decorator passes through normal execution."""
        @handle_exception
        def normal_function(x, y):
            return x + y
        
        result = normal_function(2, 3)
        assert result == 5
    
    def test_handle_exception_decorator_pyelectron_error(self):
        """Test decorator re-raises PyElectron errors as-is."""
        @handle_exception
        def function_with_pyelectron_error():
            raise IPCError("Original IPC error")
        
        with pytest.raises(IPCError) as exc_info:
            function_with_pyelectron_error()
        
        assert str(exc_info.value) == "Original IPC error"
    
    def test_handle_exception_decorator_other_error(self):
        """Test decorator converts other errors to PyElectronError."""
        @handle_exception
        def function_with_value_error():
            raise ValueError("Original value error")
        
        with pytest.raises(PyElectronError) as exc_info:
            function_with_value_error()
        
        assert "function_with_value_error" in str(exc_info.value)
        assert "Original value error" in str(exc_info.value)
        assert exc_info.value.details["original_exception"] == "ValueError"
    
    @pytest.mark.asyncio
    async def test_handle_async_exception_decorator_passthrough(self):
        """Test async decorator passes through normal execution."""
        @handle_async_exception
        async def normal_async_function(x, y):
            return x + y
        
        result = await normal_async_function(2, 3)
        assert result == 5
    
    @pytest.mark.asyncio
    async def test_handle_async_exception_decorator_pyelectron_error(self):
        """Test async decorator re-raises PyElectron errors as-is."""
        @handle_async_exception
        async def async_function_with_pyelectron_error():
            raise WebViewError("Original WebView error")
        
        with pytest.raises(WebViewError) as exc_info:
            await async_function_with_pyelectron_error()
        
        assert str(exc_info.value) == "Original WebView error"
    
    @pytest.mark.asyncio
    async def test_handle_async_exception_decorator_other_error(self):
        """Test async decorator converts other errors to PyElectronError."""
        @handle_async_exception
        async def async_function_with_runtime_error():
            raise RuntimeError("Original runtime error")
        
        with pytest.raises(PyElectronError) as exc_info:
            await async_function_with_runtime_error()
        
        assert "async_function_with_runtime_error" in str(exc_info.value)
        assert "Original runtime error" in str(exc_info.value)
        assert exc_info.value.details["original_exception"] == "RuntimeError"


class TestErrorChaining:
    """Test error chaining and context preservation."""
    
    def test_error_chaining_preserved(self):
        """Test that original exception is preserved in chain."""
        @handle_exception
        def function_with_chained_error():
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise RuntimeError("Wrapper error") from e
        
        with pytest.raises(PyElectronError) as exc_info:
            function_with_chained_error()
        
        # Check that the original exception chain is preserved
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert str(exc_info.value.__cause__) == "Wrapper error"