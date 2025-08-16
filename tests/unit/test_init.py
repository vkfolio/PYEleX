"""
Unit tests for PyElectron package initialization

Tests the main package __init__.py functionality including
platform detection, WebView availability checking, and imports.
"""

import pytest
import sys
from unittest.mock import patch, MagicMock

import pyelectron


class TestVersionInfo:
    """Test version information and constants."""
    
    def test_version_string_format(self):
        """Test that version string follows semantic versioning."""
        version = pyelectron.__version__
        assert isinstance(version, str)
        
        # Should match pattern like "0.1.0-alpha.1" or "1.2.3"
        parts = version.split('-')[0].split('.')
        assert len(parts) >= 3, f"Version should have at least 3 parts: {version}"
        
        # First three parts should be numeric
        for part in parts[:3]:
            assert part.isdigit(), f"Version part should be numeric: {part}"
    
    def test_version_info_tuple(self):
        """Test that VERSION_INFO is a tuple of integers."""
        version_info = pyelectron.VERSION_INFO
        assert isinstance(version_info, tuple)
        assert len(version_info) >= 3
        
        for part in version_info:
            assert isinstance(part, int)
    
    def test_package_metadata(self):
        """Test package metadata constants."""
        assert isinstance(pyelectron.__author__, str)
        assert isinstance(pyelectron.__email__, str)
        assert isinstance(pyelectron.__license__, str)
        assert pyelectron.__license__ == "MIT"


class TestPlatformDetection:
    """Test platform detection and WebView availability."""
    
    def test_get_platform_info_structure(self):
        """Test that platform info returns expected structure."""
        info = pyelectron.get_platform_info()
        
        assert isinstance(info, dict)
        required_keys = ['system', 'webview_available']
        for key in required_keys:
            assert key in info, f"Missing required key: {key}"
        
        assert isinstance(info['webview_available'], bool)
    
    def test_check_webview_availability_return_format(self):
        """Test WebView availability check return format."""
        available, message = pyelectron.check_webview_availability()
        
        assert isinstance(available, bool)
        assert isinstance(message, str)
        assert len(message) > 0
    
    @patch('platform.system')
    def test_platform_detection_windows(self, mock_system):
        """Test platform detection for Windows."""
        mock_system.return_value = 'Windows'
        
        # Mock the webview import
        with patch.dict(sys.modules, {'webview': MagicMock()}):
            # Reload the module to trigger platform detection
            import importlib
            importlib.reload(pyelectron)
            
            info = pyelectron.get_platform_info()
            assert info['system'] == 'Windows'
    
    @patch('platform.system')
    def test_platform_detection_macos(self, mock_system):
        """Test platform detection for macOS."""
        mock_system.return_value = 'Darwin'
        
        # Mock the objc and WebKit imports
        mock_objc = MagicMock()
        mock_webkit = MagicMock()
        mock_webkit.WKWebView = MagicMock()
        
        with patch.dict(sys.modules, {
            'objc': mock_objc,
            'WebKit': mock_webkit
        }):
            import importlib
            importlib.reload(pyelectron)
            
            info = pyelectron.get_platform_info()
            assert info['system'] == 'Darwin'
    
    @patch('platform.system')
    def test_platform_detection_linux(self, mock_system):
        """Test platform detection for Linux."""
        mock_system.return_value = 'Linux'
        
        # Mock the gi imports
        mock_gi = MagicMock()
        mock_webkit2 = MagicMock()
        
        with patch.dict(sys.modules, {
            'gi': mock_gi,
            'gi.repository': MagicMock(),
            'gi.repository.WebKit2': mock_webkit2
        }):
            import importlib
            importlib.reload(pyelectron)
            
            info = pyelectron.get_platform_info()
            assert info['system'] == 'Linux'


class TestImports:
    """Test package imports and public API."""
    
    def test_core_imports(self):
        """Test that core classes can be imported."""
        from pyelectron import (
            PyElectronApp,
            WindowConfig,
            WindowManager,
            ProcessManager
        )
        
        # Basic smoke test - classes should be importable
        assert PyElectronApp is not None
        assert WindowConfig is not None
        assert WindowManager is not None
        assert ProcessManager is not None
    
    def test_ipc_imports(self):
        """Test that IPC classes can be imported."""
        from pyelectron import (
            JSONRPCHandler,
            SharedDataManager
        )
        
        assert JSONRPCHandler is not None
        assert SharedDataManager is not None
    
    def test_security_imports(self):
        """Test that security classes can be imported."""
        from pyelectron import (
            Permission,
            PermissionManager
        )
        
        assert Permission is not None
        assert PermissionManager is not None
    
    def test_state_imports(self):
        """Test that state management classes can be imported."""
        from pyelectron import StateManager
        
        assert StateManager is not None
    
    def test_error_imports(self):
        """Test that error classes can be imported."""
        from pyelectron import (
            PyElectronError,
            IPCError,
            WebViewError,
            PermissionError,
            StateError
        )
        
        assert PyElectronError is not None
        assert IPCError is not None
        assert WebViewError is not None
        assert PermissionError is not None
        assert StateError is not None
    
    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        expected_exports = [
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
        
        for export in expected_exports:
            assert export in pyelectron.__all__, f"Missing export: {export}"


class TestConvenienceFunctions:
    """Test convenience functions for app creation."""
    
    def test_create_app_basic(self):
        """Test basic app creation."""
        app = pyelectron.create_app("TestApp")
        
        assert app is not None
        assert isinstance(app, pyelectron.PyElectronApp)
        assert app.name == "TestApp"
    
    def test_create_app_with_kwargs(self):
        """Test app creation with additional arguments."""
        app = pyelectron.create_app(
            "TestApp",
            data_dir="/tmp/test",
            development_mode=True
        )
        
        assert app is not None
        assert isinstance(app, pyelectron.PyElectronApp)
        assert app.name == "TestApp"


class TestPythonVersionValidation:
    """Test Python version validation."""
    
    @patch('sys.version_info', (3, 7, 0))
    def test_python_version_too_old(self):
        """Test that old Python versions are rejected."""
        with pytest.raises(RuntimeError) as exc_info:
            pyelectron._validate_python_version()
        
        assert "Python 3.8 or higher" in str(exc_info.value)
    
    @patch('sys.version_info', (3, 8, 0))
    def test_python_version_minimum(self):
        """Test that minimum Python version is accepted."""
        # Should not raise an exception
        pyelectron._validate_python_version()
    
    @patch('sys.version_info', (3, 12, 0))
    def test_python_version_newer(self):
        """Test that newer Python versions are accepted."""
        # Should not raise an exception
        pyelectron._validate_python_version()