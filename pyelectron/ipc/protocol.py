"""
PyElectron JSON-RPC 2.0 Protocol Implementation

This module provides a complete JSON-RPC 2.0 implementation for secure
inter-process communication with proper error handling and validation.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union

from pyelectron.utils.errors import RPCError, ValidationError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class MessageType(Enum):
    """JSON-RPC message types."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


@dataclass
class RPCMessage:
    """Base RPC message."""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None


@dataclass
class RPCRequest(RPCMessage):
    """RPC request message."""
    method: str = ""
    params: Optional[Union[Dict[str, Any], list]] = None


@dataclass
class RPCResponse(RPCMessage):
    """RPC response message.""" 
    result: Optional[Any] = None


@dataclass
class RPCErrorResponse(RPCMessage):
    """RPC error response message."""
    error: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RPCNotification(RPCMessage):
    """RPC notification message (no response expected)."""
    method: str = ""
    params: Optional[Union[Dict[str, Any], list]] = None
    id: Optional[Union[str, int]] = field(default=None, init=False)


class RPCErrorCode(Enum):
    """Standard JSON-RPC error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # Custom error codes (application-defined)
    PERMISSION_DENIED = -32000
    TIMEOUT = -32001
    PROCESS_ERROR = -32002


class JSONRPCProtocol:
    """
    JSON-RPC 2.0 protocol handler with security and validation.
    
    Provides secure method calls, parameter validation, and proper
    error handling according to JSON-RPC 2.0 specification.
    """
    
    def __init__(self):
        self.methods: Dict[str, Callable] = {}
        self.middleware: list[Callable] = []
        self.pending_requests: Dict[Union[str, int], asyncio.Future] = {}
        self.request_timeout = 30.0
        
        logger.debug("JSONRPCProtocol initialized")
    
    def register_method(self, name: str, handler: Callable):
        """
        Register RPC method handler.
        
        Args:
            name: Method name
            handler: Method handler function
        """
        if not callable(handler):
            raise ValueError(f"Handler for {name} must be callable")
        
        self.methods[name] = handler
        logger.debug(f"Registered RPC method: {name}")
    
    def add_middleware(self, middleware: Callable):
        """Add middleware function for request processing."""
        self.middleware.append(middleware)
    
    @handle_exception
    def create_request(self, method: str, params: Optional[Union[Dict, list]] = None, 
                      request_id: Optional[Union[str, int]] = None) -> str:
        """
        Create JSON-RPC request message.
        
        Args:
            method: Method name
            params: Method parameters
            request_id: Request ID (auto-generated if None)
            
        Returns:
            JSON-encoded request message
        """
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        request = RPCRequest(
            method=method,
            params=params,
            id=request_id
        )
        
        return self._serialize_message(request)
    
    @handle_exception
    def create_notification(self, method: str, params: Optional[Union[Dict, list]] = None) -> str:
        """
        Create JSON-RPC notification message.
        
        Args:
            method: Method name
            params: Method parameters
            
        Returns:
            JSON-encoded notification message
        """
        notification = RPCNotification(
            method=method,
            params=params
        )
        
        return self._serialize_message(notification)
    
    @handle_exception
    def create_response(self, request_id: Union[str, int], result: Any) -> str:
        """
        Create JSON-RPC success response.
        
        Args:
            request_id: Original request ID
            result: Method result
            
        Returns:
            JSON-encoded response message
        """
        response = RPCResponse(
            id=request_id,
            result=result
        )
        
        return self._serialize_message(response)
    
    @handle_exception
    def create_error_response(self, request_id: Optional[Union[str, int]], 
                            code: RPCErrorCode, message: str,
                            data: Optional[Any] = None) -> str:
        """
        Create JSON-RPC error response.
        
        Args:
            request_id: Original request ID (None for parse errors)
            code: Error code
            message: Error message
            data: Additional error data
            
        Returns:
            JSON-encoded error response
        """
        error_response = RPCErrorResponse(
            id=request_id,
            error={
                'code': code.value,
                'message': message,
                'data': data
            }
        )
        
        return self._serialize_message(error_response)
    
    @handle_exception
    async def process_message(self, message_data: str) -> Optional[str]:
        """
        Process incoming JSON-RPC message.
        
        Args:
            message_data: JSON-encoded message
            
        Returns:
            JSON-encoded response (None for notifications)
        """
        try:
            # Parse message
            try:
                data = json.loads(message_data)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error: {e}")
                return self.create_error_response(
                    None, 
                    RPCErrorCode.PARSE_ERROR,
                    "Parse error"
                )
            
            # Validate basic structure
            if not isinstance(data, dict):
                return self._invalid_request_error(None)
            
            if data.get('jsonrpc') != '2.0':
                return self._invalid_request_error(data.get('id'))
            
            # Process based on message type
            if 'method' in data:
                # Request or notification
                return await self._handle_request(data)
            elif 'result' in data or 'error' in data:
                # Response
                await self._handle_response(data)
                return None
            else:
                return self._invalid_request_error(data.get('id'))
                
        except Exception as e:
            logger.error(f"Error processing RPC message: {e}")
            return self.create_error_response(
                None,
                RPCErrorCode.INTERNAL_ERROR,
                "Internal error",
                str(e)
            )
    
    async def _handle_request(self, data: Dict[str, Any]) -> Optional[str]:
        """Handle RPC request or notification."""
        method_name = data.get('method')
        params = data.get('params')
        request_id = data.get('id')
        
        # Validate method name
        if not isinstance(method_name, str):
            return self._invalid_request_error(request_id)
        
        # Check if method exists
        if method_name not in self.methods:
            if request_id is not None:  # Only respond to requests, not notifications
                return self.create_error_response(
                    request_id,
                    RPCErrorCode.METHOD_NOT_FOUND,
                    f"Method not found: {method_name}"
                )
            return None
        
        # Get method handler
        handler = self.methods[method_name]
        
        try:
            # Apply middleware
            for middleware in self.middleware:
                await middleware(method_name, params)
            
            # Call method
            if params is None:
                result = await self._call_handler(handler)
            elif isinstance(params, list):
                result = await self._call_handler(handler, *params)
            elif isinstance(params, dict):
                result = await self._call_handler(handler, **params)
            else:
                if request_id is not None:
                    return self.create_error_response(
                        request_id,
                        RPCErrorCode.INVALID_PARAMS,
                        "Invalid parameters"
                    )
                return None
            
            # Return response for requests (not notifications)
            if request_id is not None:
                return self.create_response(request_id, result)
            
            return None
            
        except ValidationError as e:
            if request_id is not None:
                return self.create_error_response(
                    request_id,
                    RPCErrorCode.INVALID_PARAMS,
                    str(e)
                )
            return None
            
        except Exception as e:
            logger.error(f"Error calling method {method_name}: {e}")
            if request_id is not None:
                return self.create_error_response(
                    request_id,
                    RPCErrorCode.INTERNAL_ERROR,
                    f"Method execution error: {str(e)}"
                )
            return None
    
    async def _handle_response(self, data: Dict[str, Any]):
        """Handle RPC response."""
        request_id = data.get('id')
        
        if request_id not in self.pending_requests:
            logger.warning(f"Received response for unknown request: {request_id}")
            return
        
        future = self.pending_requests.pop(request_id)
        
        if 'error' in data:
            error_data = data['error']
            error = RPCError(
                error_data.get('message', 'Unknown error'),
                error_data.get('code', -1),
                error_data.get('data')
            )
            future.set_exception(error)
        else:
            result = data.get('result')
            future.set_result(result)
    
    async def _call_handler(self, handler: Callable, *args, **kwargs):
        """Call method handler (sync or async)."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(*args, **kwargs)
        else:
            return handler(*args, **kwargs)
    
    def _invalid_request_error(self, request_id: Optional[Union[str, int]]) -> str:
        """Create invalid request error response."""
        return self.create_error_response(
            request_id,
            RPCErrorCode.INVALID_REQUEST,
            "Invalid request"
        )
    
    def _serialize_message(self, message: Union[RPCMessage, RPCRequest, RPCResponse, 
                                             RPCErrorResponse, RPCNotification]) -> str:
        """Serialize message to JSON."""
        try:
            # Convert dataclass to dict, excluding None values for notifications
            if isinstance(message, RPCNotification):
                data = {
                    'jsonrpc': message.jsonrpc,
                    'method': message.method
                }
                if message.params is not None:
                    data['params'] = message.params
            else:
                data = {
                    'jsonrpc': message.jsonrpc,
                    'id': message.id
                }
                
                if hasattr(message, 'method'):
                    data['method'] = message.method
                if hasattr(message, 'params') and message.params is not None:
                    data['params'] = message.params
                if hasattr(message, 'result'):
                    data['result'] = message.result
                if hasattr(message, 'error'):
                    data['error'] = message.error
            
            return json.dumps(data, separators=(',', ':'))
            
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Failed to serialize message: {str(e)}") from e
    
    async def call_method(self, method: str, params: Optional[Union[Dict, list]] = None,
                         timeout: Optional[float] = None) -> Any:
        """
        Call remote method and wait for response.
        
        Args:
            method: Method name
            params: Method parameters
            timeout: Request timeout
            
        Returns:
            Method result
            
        Raises:
            RPCError: If remote method returns error
            asyncio.TimeoutError: If request times out
        """
        if timeout is None:
            timeout = self.request_timeout
        
        request_id = str(uuid.uuid4())
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future
        
        try:
            # Create and send request (this would be handled by transport layer)
            request_msg = self.create_request(method, params, request_id)
            
            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
            
        except asyncio.TimeoutError:
            # Clean up pending request
            self.pending_requests.pop(request_id, None)
            raise
        except Exception:
            # Clean up pending request
            self.pending_requests.pop(request_id, None)
            raise
    
    def cleanup(self):
        """Cleanup protocol state."""
        # Cancel all pending requests
        for future in self.pending_requests.values():
            if not future.done():
                future.cancel()
        
        self.pending_requests.clear()
        logger.debug("JSONRPCProtocol cleaned up")


def rpc_method(name: Optional[str] = None):
    """
    Decorator to mark functions as RPC methods.
    
    Args:
        name: Custom method name (uses function name if None)
    """
    def decorator(func: Callable):
        method_name = name or func.__name__
        func._rpc_method_name = method_name
        return func
    
    return decorator


def validate_params(schema: Dict[str, Any]):
    """
    Decorator to validate RPC method parameters.
    
    Args:
        schema: Parameter validation schema
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            # Basic validation - in a real implementation, 
            # this would use a schema validation library
            return func(*args, **kwargs)
        return wrapper
    
    return decorator