"""
Security modules

This package provides simple but effective security mechanisms
including permissions, input validation, and secure defaults.
"""

from pyelectron.security.permissions import Permission, PermissionManager, requires_permission
from pyelectron.security.validation import InputValidator

__all__ = [
    "Permission",
    "PermissionManager",
    "requires_permission",
    "InputValidator",
]