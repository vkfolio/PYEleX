"""
PyElectron Platform Utilities

This module provides platform detection, WebView availability checking,
and cross-platform utility functions.
"""

import os
import platform
import sys
from typing import Dict, Any, Tuple

from typing import Optional
from pyelectron.utils.errors import PlatformError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class PlatformUtils:
    """Platform utilities and WebView detection."""
    
    def __init__(self):
        self._platform_info: Optional[Dict[str, Any]] = None
        self._webview_info: Optional[Dict[str, Any]] = None
    
    @handle_exception
    def get_platform_info(self) -> Dict[str, Any]:
        """
        Get comprehensive platform information.
        
        Returns:
            Dict containing platform details
        """
        if self._platform_info is None:
            self._platform_info = self._detect_platform()
        
        return self._platform_info.copy()
    
    def _detect_platform(self) -> Dict[str, Any]:
        """Detect current platform and capabilities."""
        system = platform.system()
        
        info = {
            'system': system,
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'architecture': platform.architecture(),
            'python_version': sys.version,
            'python_implementation': platform.python_implementation(),
            'platform_string': platform.platform(),
        }
        
        # Add system-specific information
        if system == 'Windows':
            info.update(self._get_windows_info())
        elif system == 'Darwin':  # macOS
            info.update(self._get_macos_info())
        elif system == 'Linux':
            info.update(self._get_linux_info())
        
        # Check WebView availability
        webview_info = self._check_webview_availability()
        info.update(webview_info)
        
        return info
    
    def _get_windows_info(self) -> Dict[str, Any]:
        """Get Windows-specific information."""
        info = {
            'windows_version': platform.win32_ver(),
            'windows_edition': platform.win32_edition() if hasattr(platform, 'win32_edition') else None,
        }
        
        # Check Windows version for WebView2 compatibility
        try:
            import winreg
            # Check Windows 10 version
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                               r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            build = winreg.QueryValueEx(key, "CurrentBuild")[0]
            winreg.CloseKey(key)
            
            info['windows_build'] = build
            info['webview2_supported'] = int(build) >= 17763  # Windows 10 1809+
            
        except Exception as e:
            logger.warning(f"Could not determine Windows build: {e}")
            info['webview2_supported'] = False
        
        return info
    
    def _get_macos_info(self) -> Dict[str, Any]:
        """Get macOS-specific information."""
        info = {
            'macos_version': platform.mac_ver(),
        }
        
        # Check macOS version for WKWebView support
        try:
            version_tuple = platform.mac_ver()[0].split('.')
            major = int(version_tuple[0])
            minor = int(version_tuple[1]) if len(version_tuple) > 1 else 0
            
            info['macos_major'] = major
            info['macos_minor'] = minor
            # WKWebView available in macOS 10.10+
            info['wkwebview_supported'] = major > 10 or (major == 10 and minor >= 10)
            
        except Exception as e:
            logger.warning(f"Could not determine macOS version: {e}")
            info['wkwebview_supported'] = False
        
        return info
    
    def _get_linux_info(self) -> Dict[str, Any]:
        """Get Linux-specific information."""
        info = {
            'linux_distribution': platform.freedesktop_os_release() if hasattr(platform, 'freedesktop_os_release') else None,
        }
        
        # Check for WebKit2GTK availability
        try:
            # Try to detect package manager and WebKit installation
            webkit_installed = False
            
            # Check common package managers
            package_managers = [
                ('dpkg', 'dpkg -l libwebkit2gtk-4.0-37'),  # Debian/Ubuntu
                ('rpm', 'rpm -q webkit2gtk3'),            # Red Hat/Fedora
                ('pacman', 'pacman -Q webkit2gtk'),       # Arch
            ]
            
            for pm_name, check_cmd in package_managers:
                if self._command_exists(pm_name):
                    if os.system(f"{check_cmd} >/dev/null 2>&1") == 0:
                        webkit_installed = True
                        info['webkit_package_manager'] = pm_name
                        break
            
            info['webkit2gtk_installed'] = webkit_installed
            
        except Exception as e:
            logger.warning(f"Could not check WebKit2GTK installation: {e}")
            info['webkit2gtk_installed'] = False
        
        return info
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        return os.system(f"which {command} >/dev/null 2>&1") == 0
    
    def _check_webview_availability(self) -> Dict[str, Any]:
        """Check WebView availability for current platform."""
        system = platform.system()
        
        webview_info = {
            'webview_available': False,
            'webview_backend': None,
            'webview_error': None,
        }
        
        try:
            if system == 'Windows':
                webview_info.update(self._check_webview2())
            elif system == 'Darwin':
                webview_info.update(self._check_wkwebview())
            elif system == 'Linux':
                webview_info.update(self._check_webkit2gtk())
            else:
                webview_info['webview_error'] = f"Unsupported platform: {system}"
                
        except Exception as e:
            webview_info['webview_error'] = f"Error checking WebView: {str(e)}"
            logger.error(f"WebView detection error: {e}")
        
        return webview_info
    
    def _check_webview2(self) -> Dict[str, Any]:
        """Check WebView2 availability on Windows."""
        try:
            import webview
            return {
                'webview_available': True,
                'webview_backend': 'webview2',
                'webview_library': 'pywebview',
            }
        except ImportError:
            return {
                'webview_available': False,
                'webview_error': (
                    "WebView2 not available. Please install:\n"
                    "pip install pywebview[cef]\n\n"
                    "Note: WebView2 Runtime should be pre-installed on Windows 10+"
                ),
            }
    
    def _check_wkwebview(self) -> Dict[str, Any]:
        """Check WKWebView availability on macOS."""
        try:
            import objc
            from WebKit import WKWebView
            return {
                'webview_available': True,
                'webview_backend': 'wkwebview',
                'webview_library': 'pyobjc-framework-WebKit',
            }
        except ImportError:
            return {
                'webview_available': False,
                'webview_error': (
                    "WKWebView not available. Please install:\n"
                    "pip install pyobjc-framework-WebKit pyobjc-framework-Cocoa"
                ),
            }
    
    def _check_webkit2gtk(self) -> Dict[str, Any]:
        """Check WebKit2GTK availability on Linux."""
        try:
            import gi
            gi.require_version('WebKit2', '4.0')
            from gi.repository import WebKit2
            return {
                'webview_available': True,
                'webview_backend': 'webkit2gtk',
                'webview_library': 'PyGObject',
            }
        except (ImportError, ValueError):
            return {
                'webview_available': False,
                'webview_error': (
                    "WebKit2GTK not available. Please install:\n"
                    "Ubuntu/Debian: sudo apt install python3-gi webkit2gtk-4.0\n"
                    "Fedora: sudo dnf install python3-gobject webkit2gtk4\n"
                    "Arch: sudo pacman -S python-gobject webkit2gtk\n"
                    "Then: pip install PyGObject"
                ),
            }
    
    def check_webview_availability(self) -> Tuple[bool, str]:
        """
        Check if WebView is available on current platform.
        
        Returns:
            Tuple of (available, message)
        """
        info = self.get_platform_info()
        
        if info['webview_available']:
            return True, f"WebView available: {info['webview_backend']}"
        else:
            error_msg = info.get('webview_error', 'WebView not available')
            return False, error_msg
    
    def get_recommended_setup(self) -> str:
        """Get platform-specific setup recommendations."""
        system = platform.system()
        
        if system == 'Windows':
            return (
                "Windows Setup:\n"
                "1. Ensure Windows 10 1809+ (for WebView2)\n"
                "2. Install: pip install pyelectron[windows]\n"
                "3. WebView2 Runtime is usually pre-installed"
            )
        elif system == 'Darwin':
            return (
                "macOS Setup:\n"
                "1. Ensure macOS 10.10+ (for WKWebView)\n"
                "2. Install: pip install pyelectron[macos]\n"
                "3. WKWebView is built into macOS"
            )
        elif system == 'Linux':
            return (
                "Linux Setup:\n"
                "1. Install system packages:\n"
                "   Ubuntu/Debian: sudo apt install python3-gi webkit2gtk-4.0\n"
                "   Fedora: sudo dnf install python3-gobject webkit2gtk4\n"
                "   Arch: sudo pacman -S python-gobject webkit2gtk\n"
                "2. Install: pip install pyelectron[linux]"
            )
        else:
            return f"Platform {system} is not currently supported by PyElectron"
    
    def validate_environment(self) -> Dict[str, Any]:
        """
        Validate the current environment for PyElectron.
        
        Returns:
            Dict containing validation results
        """
        results = {
            'platform_supported': True,
            'python_version_ok': True,
            'webview_available': False,
            'issues': [],
            'recommendations': [],
        }
        
        # Check Python version
        if sys.version_info < (3, 8):
            results['python_version_ok'] = False
            results['issues'].append(
                f"Python 3.8+ required, found {sys.version_info[:2]}"
            )
            results['recommendations'].append("Upgrade Python to 3.8 or higher")
        
        # Check platform support
        system = platform.system()
        if system not in ['Windows', 'Darwin', 'Linux']:
            results['platform_supported'] = False
            results['issues'].append(f"Platform {system} is not supported")
        
        # Check WebView availability
        webview_available, webview_message = self.check_webview_availability()
        results['webview_available'] = webview_available
        
        if not webview_available:
            results['issues'].append(f"WebView not available: {webview_message}")
            results['recommendations'].append(self.get_recommended_setup())
        
        return results
    
    def is_development_environment(self) -> bool:
        """Check if running in development environment."""
        return (
            os.getenv('PYELECTRON_DEV') == '1' or
            os.getenv('PYELECTRON_DEBUG') == '1' or
            os.getenv('DEVELOPMENT') == '1' or
            '--dev' in sys.argv
        )
    
    def get_data_directory(self, app_name: str) -> str:
        """Get platform-appropriate data directory."""
        system = platform.system()
        
        if system == 'Windows':
            base = os.getenv('APPDATA', os.path.expanduser('~/AppData/Roaming'))
        elif system == 'Darwin':
            base = os.path.expanduser('~/Library/Application Support')
        else:  # Linux and others
            base = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
        
        return os.path.join(base, app_name)
    
    def get_config_directory(self, app_name: str) -> str:
        """Get platform-appropriate config directory."""
        system = platform.system()
        
        if system == 'Windows':
            base = os.getenv('APPDATA', os.path.expanduser('~/AppData/Roaming'))
        elif system == 'Darwin':
            base = os.path.expanduser('~/Library/Preferences')
        else:  # Linux and others
            base = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        
        return os.path.join(base, app_name)