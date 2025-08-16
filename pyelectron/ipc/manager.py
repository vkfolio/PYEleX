"""
PyElectron IPC Manager

This module provides high-level IPC management, combining transport,
protocol, and security layers into a unified interface.
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Set, Union

from .transport import NativeTransport, TransportConfig, BaseTransport
from .protocol import JSONRPCProtocol, rpc_method
from .security import IPCSecurity, SecurityConfig, create_secure_config
from pyelectron.utils.errors import IPCError, SecurityError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConnectionInfo:
    """Information about an IPC connection."""
    
    connection_id: str
    client_id: str
    transport: BaseTransport
    created_at: float
    last_activity: float
    is_authenticated: bool = False
    permissions: Set[str] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = set()


class IPCManager:
    """
    High-level IPC manager combining transport, protocol, and security.
    
    Provides a simple interface for setting up secure IPC communication
    between PyElectron processes.
    """
    
    def __init__(self, name: str, security_config: Optional[SecurityConfig] = None):
        """
        Initialize IPC manager.
        
        Args:
            name: IPC endpoint name
            security_config: Security configuration
        """
        self.name = name
        self.security_config = security_config or SecurityConfig()
        
        # Core components
        self.transport_config = TransportConfig(name=name)
        self.transport: Optional[BaseTransport] = None
        self.protocol = JSONRPCProtocol()
        self.security = IPCSecurity(self.security_config) if security_config else None
        
        # Connection management
        self.connections: Dict[str, ConnectionInfo] = {}
        self.is_server = False
        self.is_connected = False
        self.server_address: Optional[str] = None
        
        # Message handling
        self.message_handlers: Dict[str, Callable] = {}
        self.middleware: list[Callable] = []
        
        # Background tasks
        self.server_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        logger.debug(f"IPCManager initialized: {name}")
    
    @handle_exception
    async def start_server(self) -> str:
        """
        Start IPC server.
        
        Returns:
            str: Server address for clients to connect to
        """
        if self.is_server:
            raise IPCError("Server already started")
        
        logger.info(f"Starting IPC server: {self.name}")
        
        # Create transport
        self.transport = NativeTransport.create(self.transport_config)
        
        # Start transport server
        self.server_address = await self.transport.start_server()
        self.is_server = True
        self.is_connected = True
        
        # Start background tasks
        self.server_task = asyncio.create_task(self._server_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"IPC server started: {self.server_address}")
        return self.server_address
    
    @handle_exception
    async def connect_to_server(self, server_address: str) -> None:
        """
        Connect to IPC server.
        
        Args:
            server_address: Server address to connect to
        """
        if self.is_connected:
            raise IPCError("Already connected")
        
        logger.info(f"Connecting to IPC server: {server_address}")
        
        # Create transport
        self.transport = NativeTransport.create(self.transport_config)
        
        # Connect to server
        await self.transport.connect(server_address)
        self.is_connected = True
        
        # Start message processing loop
        self.server_task = asyncio.create_task(self._client_loop())
        
        logger.info(f"Connected to IPC server: {server_address}")
    
    async def _server_loop(self):
        """Main server loop handling incoming connections."""
        logger.debug("Server loop started")
        
        try:
            while self.is_connected:
                try:
                    # This is a simplified version - real implementation would
                    # handle multiple concurrent connections
                    if hasattr(self.transport, 'connections') and self.transport.connections:
                        for client_id, (reader, writer) in self.transport.connections.items():
                            if client_id not in self.connections:
                                # New connection
                                connection_info = ConnectionInfo(
                                    connection_id=str(uuid.uuid4()),
                                    client_id=client_id,
                                    transport=self.transport,
                                    created_at=asyncio.get_event_loop().time(),
                                    last_activity=asyncio.get_event_loop().time()
                                )
                                self.connections[client_id] = connection_info
                                logger.info(f"New client connected: {client_id}")
                            
                            # Handle messages from this client
                            try:
                                # Check if data is available
                                data = await asyncio.wait_for(
                                    self.transport.receive(),
                                    timeout=0.1
                                )
                                
                                if data:
                                    await self._handle_message(data, client_id)
                                    
                            except asyncio.TimeoutError:
                                # No data available, continue
                                continue
                            except Exception as e:
                                logger.error(f"Error handling message from {client_id}: {e}")
                    
                    await asyncio.sleep(0.1)  # Prevent busy loop
                    
                except Exception as e:
                    logger.error(f"Server loop error: {e}")
                    await asyncio.sleep(1.0)
                    
        except asyncio.CancelledError:
            logger.debug("Server loop cancelled")
        except Exception as e:
            logger.error(f"Server loop fatal error: {e}")
    
    async def _client_loop(self):
        """Main client loop handling incoming messages."""
        logger.debug("Client loop started")
        
        try:
            while self.is_connected:
                try:
                    # Receive message from server
                    data = await self.transport.receive()
                    
                    if data:
                        await self._handle_message(data, "server")
                        
                except Exception as e:
                    logger.error(f"Client loop error: {e}")
                    break
                    
        except asyncio.CancelledError:
            logger.debug("Client loop cancelled")
        except Exception as e:
            logger.error(f"Client loop fatal error: {e}")
    
    async def _handle_message(self, data: bytes, client_id: str):
        """Handle incoming message."""
        try:
            message = data.decode('utf-8')
            
            # Security validation
            if self.security:
                validated_data = self.security.validate_incoming_message(
                    message, client_id
                )
            else:
                import json
                validated_data = json.loads(message)
            
            # Update connection activity
            if client_id in self.connections:
                self.connections[client_id].last_activity = asyncio.get_event_loop().time()
            
            # Process with protocol
            response = await self.protocol.process_message(message)
            
            # Send response if needed
            if response and self.transport:
                await self.transport.send(response.encode('utf-8'))
                
        except SecurityError as e:
            logger.warning(f"Security error from {client_id}: {e}")
            # Optionally disconnect client
        except Exception as e:
            logger.error(f"Error handling message from {client_id}: {e}")
    
    async def _cleanup_loop(self):
        """Background cleanup loop."""
        while self.is_connected:
            try:
                # Cleanup old connections
                current_time = asyncio.get_event_loop().time()
                timeout = 300.0  # 5 minutes
                
                for client_id in list(self.connections.keys()):
                    conn_info = self.connections[client_id]
                    if current_time - conn_info.last_activity > timeout:
                        logger.info(f"Removing inactive connection: {client_id}")
                        del self.connections[client_id]
                
                # Cleanup security
                if self.security:
                    self.security.cleanup()
                
                await asyncio.sleep(60.0)  # Run every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(60.0)
    
    def register_method(self, name: str, handler: Callable):
        """
        Register RPC method handler.
        
        Args:
            name: Method name
            handler: Handler function
        """
        self.protocol.register_method(name, handler)
        logger.debug(f"Registered IPC method: {name}")
    
    def register_methods_from_object(self, obj: Any):
        """
        Register all RPC methods from an object.
        
        Args:
            obj: Object containing RPC methods
        """
        for attr_name in dir(obj):
            attr = getattr(obj, attr_name)
            if hasattr(attr, '_rpc_method_name'):
                method_name = attr._rpc_method_name
                self.register_method(method_name, attr)
    
    @handle_exception
    async def call_method(self, method: str, params: Optional[Union[Dict, list]] = None,
                         timeout: float = 30.0) -> Any:
        """
        Call remote method.
        
        Args:
            method: Method name
            params: Method parameters
            timeout: Request timeout
            
        Returns:
            Method result
        """
        if not self.is_connected:
            raise IPCError("Not connected")
        
        # Create request message
        request_msg = self.protocol.create_request(method, params)
        
        # Send message
        await self.transport.send(request_msg.encode('utf-8'))
        
        # For simplicity, this implementation doesn't handle responses
        # In a complete implementation, this would wait for the response
        logger.debug(f"Called remote method: {method}")
        
        return None  # Placeholder
    
    @handle_exception
    async def send_notification(self, method: str, params: Optional[Union[Dict, list]] = None):
        """
        Send notification (no response expected).
        
        Args:
            method: Method name
            params: Method parameters
        """
        if not self.is_connected:
            raise IPCError("Not connected")
        
        # Create notification message
        notification_msg = self.protocol.create_notification(method, params)
        
        # Send message
        await self.transport.send(notification_msg.encode('utf-8'))
        
        logger.debug(f"Sent notification: {method}")
    
    def get_connection_info(self, client_id: str) -> Optional[ConnectionInfo]:
        """Get connection information."""
        return self.connections.get(client_id)
    
    def list_connections(self) -> Dict[str, ConnectionInfo]:
        """Get all active connections."""
        return self.connections.copy()
    
    async def disconnect_client(self, client_id: str):
        """Disconnect specific client."""
        if client_id in self.connections:
            del self.connections[client_id]
            logger.info(f"Disconnected client: {client_id}")
    
    @handle_exception
    async def shutdown(self):
        """Shutdown IPC manager."""
        logger.info(f"Shutting down IPC manager: {self.name}")
        
        self.is_connected = False
        
        # Cancel background tasks
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close transport
        if self.transport:
            await self.transport.close()
        
        # Cleanup protocol
        self.protocol.cleanup()
        
        # Clear connections
        self.connections.clear()
        
        logger.info("IPC manager shutdown complete")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()


def create_ipc_manager(name: str, auth_token: Optional[str] = None, 
                      **security_kwargs) -> IPCManager:
    """
    Create IPC manager with secure defaults.
    
    Args:
        name: IPC endpoint name
        auth_token: Authentication token
        **security_kwargs: Additional security configuration
        
    Returns:
        IPCManager: Configured IPC manager
    """
    if auth_token:
        security_config = create_secure_config(auth_token, **security_kwargs)
    else:
        security_config = SecurityConfig(require_auth_token=False, **security_kwargs)
    
    return IPCManager(name, security_config)