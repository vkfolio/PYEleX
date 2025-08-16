"""
PyElectron Permission Management

This module provides a simple but effective permission system
for controlling access to system resources.
"""

from enum import Enum
from functools import wraps
from typing import Set, Dict, Callable, Any

from pyelectron.utils.errors import PermissionError as PyElectronPermissionError
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class Permission(Enum):
    """Simple permission enumeration."""
    
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    NETWORK = "network"
    SYSTEM = "system"
    CLIPBOARD = "clipboard"
    CAMERA = "camera"
    MICROPHONE = "microphone"
    LOCATION = "location"
    NOTIFICATIONS = "notifications"


class PermissionManager:
    """
    Simple permission system without complex capabilities.
    
    Provides basic permission management with grant/deny semantics
    and decorator-based enforcement.
    """
    
    def __init__(self):
        self.granted: Set[Permission] = set()
        self.denied: Set[Permission] = set()
        self.session_permissions: Set[Permission] = set()
        
        logger.debug("PermissionManager initialized")
    
    def grant(self, *permissions: Permission, persistent: bool = True):
        """
        Grant permissions.
        
        Args:
            *permissions: Permissions to grant
            persistent: Whether to persist across sessions
        """
        for perm in permissions:
            if persistent:
                self.granted.add(perm)
                self.denied.discard(perm)
            else:
                self.session_permissions.add(perm)
            
            logger.debug(f"Granted permission: {perm.value}")
    
    def deny(self, *permissions: Permission):
        """
        Deny permissions.
        
        Args:
            *permissions: Permissions to deny
        """
        for perm in permissions:
            self.denied.add(perm)
            self.granted.discard(perm)
            self.session_permissions.discard(perm)
            
            logger.debug(f"Denied permission: {perm.value}")
    
    def check(self, permission: Permission) -> bool:
        """
        Check if permission is granted.
        
        Args:
            permission: Permission to check
            
        Returns:
            bool: True if granted
        """
        return (
            permission in self.granted or 
            permission in self.session_permissions
        ) and permission not in self.denied
    
    def require(self, permission: Permission):
        """
        Require permission or raise error.
        
        Args:
            permission: Required permission
            
        Raises:
            PermissionError: If permission not granted
        """
        if not self.check(permission):
            raise PyElectronPermissionError(
                f"Permission denied: {permission.value}",
                details={'permission': permission.value}
            )
    
    def revoke(self, *permissions: Permission):
        """Revoke permissions."""
        for perm in permissions:
            self.granted.discard(perm)
            self.session_permissions.discard(perm)
            logger.debug(f"Revoked permission: {perm.value}")
    
    def list_granted(self) -> Set[Permission]:
        """Get all granted permissions."""
        return self.granted.union(self.session_permissions) - self.denied
    
    def list_denied(self) -> Set[Permission]:
        """Get all denied permissions."""
        return self.denied.copy()
    
    def reset(self):
        """Reset all permissions."""
        self.granted.clear()
        self.denied.clear()
        self.session_permissions.clear()
        logger.info("All permissions reset")


def requires_permission(permission: Permission):
    """
    Decorator to check permissions.
    
    Args:
        permission: Required permission
        
    Example:
        @requires_permission(Permission.FILE_READ)
        async def read_file(self, path):
            # Implementation
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            if hasattr(self, 'permission_manager'):
                self.permission_manager.require(permission)
            elif hasattr(self, 'permissions'):
                self.permissions.require(permission)
            else:
                # Try to find permission manager in app
                if hasattr(self, 'app') and hasattr(self.app, 'permission_manager'):
                    self.app.permission_manager.require(permission)
                else:
                    logger.warning(f"No permission manager found for {func.__name__}")
            
            return await func(self, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            if hasattr(self, 'permission_manager'):
                self.permission_manager.require(permission)
            elif hasattr(self, 'permissions'):
                self.permissions.require(permission)
            else:
                # Try to find permission manager in app
                if hasattr(self, 'app') and hasattr(self.app, 'permission_manager'):
                    self.app.permission_manager.require(permission)
                else:
                    logger.warning(f"No permission manager found for {func.__name__}")
            
            return func(self, *args, **kwargs)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator