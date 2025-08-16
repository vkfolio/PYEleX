"""
Security modules

This package provides simple but effective security mechanisms
including permissions and secure defaults.
"""

from pyelectron.security.permissions import Permission, PermissionManager, requires_permission

__all__ = [
    "Permission",
    "PermissionManager",
    "requires_permission",
]