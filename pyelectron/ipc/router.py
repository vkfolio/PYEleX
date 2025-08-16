"""
PyElectron IPC Router

This module provides message routing and handler registry for organizing
IPC method handlers across different service modules.
"""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .protocol import rpc_method
from pyelectron.utils.errors import RPCError, ValidationError
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MethodInfo:
    """Information about a registered RPC method."""
    
    name: str
    handler: Callable
    module: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    return_type: Optional[str] = None
    is_async: bool = False
    requires_auth: bool = False
    permissions: Set[str] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = set()
        
        # Auto-detect if handler is async
        self.is_async = asyncio.iscoroutinefunction(self.handler)
        
        # Extract parameter information
        if self.parameters is None:
            self.parameters = self._extract_parameters()
    
    def _extract_parameters(self) -> Dict[str, Any]:
        """Extract parameter information from handler signature."""
        try:
            sig = inspect.signature(self.handler)
            params = {}
            
            for name, param in sig.parameters.items():
                # Skip 'self' parameter
                if name == 'self':
                    continue
                
                param_info = {
                    'name': name,
                    'type': param.annotation if param.annotation != inspect.Parameter.empty else 'Any',
                    'default': param.default if param.default != inspect.Parameter.empty else None,
                    'required': param.default == inspect.Parameter.empty
                }
                params[name] = param_info
            
            return params
            
        except Exception as e:
            logger.warning(f"Failed to extract parameters for {self.name}: {e}")
            return {}


class ServiceRegistry:
    """Registry for organizing RPC methods by service modules."""
    
    def __init__(self):
        self.services: Dict[str, Dict[str, MethodInfo]] = {}
        self.global_methods: Dict[str, MethodInfo] = {}
        self.middleware: List[Callable] = []
        
        logger.debug("ServiceRegistry initialized")
    
    def register_service(self, service_name: str, service_obj: Any, 
                        prefix: Optional[str] = None):
        """
        Register all RPC methods from a service object.
        
        Args:
            service_name: Name of the service
            service_obj: Service object containing RPC methods
            prefix: Optional method name prefix
        """
        if service_name in self.services:
            logger.warning(f"Service {service_name} already registered, overwriting")
        
        self.services[service_name] = {}
        
        # Find all RPC methods in the service object
        for attr_name in dir(service_obj):
            attr = getattr(service_obj, attr_name)
            
            # Check if it's an RPC method
            if hasattr(attr, '_rpc_method_name'):
                method_name = attr._rpc_method_name
                
                # Add prefix if specified
                if prefix:
                    method_name = f"{prefix}.{method_name}"
                
                # Create method info
                method_info = MethodInfo(
                    name=method_name,
                    handler=attr,
                    module=service_name,
                    description=getattr(attr, '__doc__', None)
                )
                
                # Check for special attributes
                if hasattr(attr, '_requires_auth'):
                    method_info.requires_auth = attr._requires_auth
                
                if hasattr(attr, '_permissions'):
                    method_info.permissions = set(attr._permissions)
                
                self.services[service_name][method_name] = method_info
                self.global_methods[method_name] = method_info
                
                logger.debug(f"Registered method: {method_name} from {service_name}")
    
    def register_method(self, name: str, handler: Callable, service_name: str = "default",
                       description: Optional[str] = None, requires_auth: bool = False,
                       permissions: Optional[Set[str]] = None):
        """
        Register individual RPC method.
        
        Args:
            name: Method name
            handler: Method handler
            service_name: Service name
            description: Method description
            requires_auth: Whether method requires authentication
            permissions: Required permissions
        """
        method_info = MethodInfo(
            name=name,
            handler=handler,
            module=service_name,
            description=description,
            requires_auth=requires_auth,
            permissions=permissions or set()
        )
        
        if service_name not in self.services:
            self.services[service_name] = {}
        
        self.services[service_name][name] = method_info
        self.global_methods[name] = method_info
        
        logger.debug(f"Registered method: {name}")
    
    def unregister_service(self, service_name: str):
        """Unregister entire service."""
        if service_name in self.services:
            # Remove methods from global registry
            for method_name in self.services[service_name]:
                self.global_methods.pop(method_name, None)
            
            # Remove service
            del self.services[service_name]
            logger.debug(f"Unregistered service: {service_name}")
    
    def unregister_method(self, name: str):
        """Unregister individual method."""
        # Remove from global registry
        method_info = self.global_methods.pop(name, None)
        
        if method_info:
            # Remove from service registry
            service_name = method_info.module
            if service_name in self.services:
                self.services[service_name].pop(name, None)
            
            logger.debug(f"Unregistered method: {name}")
    
    def get_method(self, name: str) -> Optional[MethodInfo]:
        """Get method information."""
        return self.global_methods.get(name)
    
    def list_methods(self, service_name: Optional[str] = None) -> Dict[str, MethodInfo]:
        """
        List registered methods.
        
        Args:
            service_name: Optional service name filter
            
        Returns:
            Dict of method name to MethodInfo
        """
        if service_name:
            return self.services.get(service_name, {}).copy()
        else:
            return self.global_methods.copy()
    
    def list_services(self) -> List[str]:
        """List registered service names."""
        return list(self.services.keys())
    
    def get_service_info(self, service_name: str) -> Dict[str, Any]:
        """Get information about a service."""
        if service_name not in self.services:
            return {}
        
        methods = self.services[service_name]
        
        return {
            'name': service_name,
            'method_count': len(methods),
            'methods': {name: {
                'description': info.description,
                'parameters': info.parameters,
                'requires_auth': info.requires_auth,
                'permissions': list(info.permissions)
            } for name, info in methods.items()}
        }


class MessageRouter:
    """Routes IPC messages to appropriate handlers with middleware support."""
    
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.request_middleware: List[Callable] = []
        self.response_middleware: List[Callable] = []
        self.error_handlers: Dict[str, Callable] = {}
        
        logger.debug("MessageRouter initialized")
    
    def add_request_middleware(self, middleware: Callable):
        """
        Add request middleware.
        
        Middleware signature: async def middleware(method_name, params, context)
        """
        self.request_middleware.append(middleware)
    
    def add_response_middleware(self, middleware: Callable):
        """
        Add response middleware.
        
        Middleware signature: async def middleware(method_name, result, context)
        """
        self.response_middleware.append(middleware)
    
    def add_error_handler(self, error_type: str, handler: Callable):
        """
        Add error handler for specific error types.
        
        Args:
            error_type: Error type (e.g., 'ValidationError', 'PermissionError')
            handler: Error handler function
        """
        self.error_handlers[error_type] = handler
    
    async def route_message(self, method_name: str, params: Optional[Union[Dict, List]] = None,
                           context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Route message to appropriate handler.
        
        Args:
            method_name: Method name to call
            params: Method parameters
            context: Request context (client info, auth, etc.)
            
        Returns:
            Method result
            
        Raises:
            RPCError: If method not found or execution fails
        """
        if context is None:
            context = {}
        
        # Get method info
        method_info = self.registry.get_method(method_name)
        if not method_info:
            raise RPCError(f"Method not found: {method_name}", code=-32601)
        
        try:
            # Run request middleware
            for middleware in self.request_middleware:
                await self._call_middleware(middleware, method_name, params, context)
            
            # Validate method access
            await self._validate_method_access(method_info, context)
            
            # Call method handler
            result = await self._call_method_handler(method_info, params)
            
            # Run response middleware
            for middleware in self.response_middleware:
                await self._call_middleware(middleware, method_name, result, context)
            
            return result
            
        except Exception as e:
            # Handle errors
            return await self._handle_error(e, method_name, context)
    
    async def _validate_method_access(self, method_info: MethodInfo, 
                                    context: Dict[str, Any]):
        """Validate method access based on authentication and permissions."""
        # Check authentication requirement
        if method_info.requires_auth:
            if not context.get('authenticated', False):
                raise RPCError("Authentication required", code=-32000)
        
        # Check permissions
        if method_info.permissions:
            user_permissions = set(context.get('permissions', []))
            required_permissions = method_info.permissions
            
            if not required_permissions.issubset(user_permissions):
                missing = required_permissions - user_permissions
                raise RPCError(
                    f"Insufficient permissions. Missing: {list(missing)}", 
                    code=-32000
                )
    
    async def _call_method_handler(self, method_info: MethodInfo, 
                                 params: Optional[Union[Dict, List]]) -> Any:
        """Call the actual method handler."""
        handler = method_info.handler
        
        try:
            if params is None:
                # No parameters
                if method_info.is_async:
                    return await handler()
                else:
                    return handler()
            
            elif isinstance(params, list):
                # Positional parameters
                if method_info.is_async:
                    return await handler(*params)
                else:
                    return handler(*params)
            
            elif isinstance(params, dict):
                # Named parameters
                if method_info.is_async:
                    return await handler(**params)
                else:
                    return handler(**params)
            
            else:
                raise ValidationError("Parameters must be array or object")
                
        except TypeError as e:
            # Parameter mismatch
            raise ValidationError(f"Invalid parameters for {method_info.name}: {str(e)}")
    
    async def _call_middleware(self, middleware: Callable, *args):
        """Call middleware function (sync or async)."""
        if asyncio.iscoroutinefunction(middleware):
            await middleware(*args)
        else:
            middleware(*args)
    
    async def _handle_error(self, error: Exception, method_name: str, 
                          context: Dict[str, Any]) -> None:
        """Handle method execution errors."""
        error_type = type(error).__name__
        
        # Check for custom error handler
        if error_type in self.error_handlers:
            handler = self.error_handlers[error_type]
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(error, method_name, context)
                else:
                    handler(error, method_name, context)
            except Exception as handler_error:
                logger.error(f"Error handler failed: {handler_error}")
        
        # Log error
        logger.error(f"Method {method_name} failed: {error}")
        
        # Re-raise as RPCError if not already
        if isinstance(error, RPCError):
            raise
        elif isinstance(error, ValidationError):
            raise RPCError(str(error), code=-32602)
        else:
            raise RPCError(f"Internal error: {str(error)}", code=-32603)


# Decorators for method registration
def requires_auth(func: Callable) -> Callable:
    """Decorator to mark method as requiring authentication."""
    func._requires_auth = True
    return func


def requires_permissions(*permissions: str):
    """Decorator to specify required permissions for method."""
    def decorator(func: Callable) -> Callable:
        func._permissions = permissions
        return func
    return decorator


def service_method(name: Optional[str] = None, description: Optional[str] = None):
    """
    Decorator to mark method as RPC service method with additional metadata.
    
    Args:
        name: Custom method name
        description: Method description
    """
    def decorator(func: Callable) -> Callable:
        # Apply base RPC method decorator
        func = rpc_method(name)(func)
        
        # Add additional metadata
        if description:
            func.__doc__ = description
        
        return func
    
    return decorator


# Example service base class
class BaseService:
    """Base class for RPC services."""
    
    def __init__(self, name: str):
        self.service_name = name
        self.logger = get_logger(f"{__name__}.{name}")
    
    @service_method("ping", "Health check method")
    def ping(self) -> str:
        """Basic health check."""
        return "pong"
    
    @service_method("get_service_info", "Get service information")
    def get_service_info(self) -> Dict[str, Any]:
        """Get information about this service."""
        return {
            'name': self.service_name,
            'methods': [attr for attr in dir(self) if hasattr(getattr(self, attr), '_rpc_method_name')]
        }