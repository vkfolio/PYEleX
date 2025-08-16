"""
Core PyElectron modules

This package contains the fundamental components of PyElectron:
- Application lifecycle management
- Process management and coordination
- Window management and WebView integration
"""

from pyelectron.core.app import PyElectronApp
from pyelectron.core.process import ProcessManager, ProcessConfig, ProcessType
from pyelectron.core.window import WindowConfig, WindowManager

__all__ = [
    "PyElectronApp",
    "ProcessManager",
    "ProcessConfig", 
    "ProcessType",
    "WindowConfig",
    "WindowManager",
]