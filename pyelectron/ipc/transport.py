"""
PyElectron Native Transport Layer

This module provides platform-specific IPC transport using Unix sockets
on Unix-like systems and named pipes on Windows.
"""

import asyncio
import os
import platform
import socket
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union

from pyelectron.utils.errors import IPCError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TransportConfig:
    """Configuration for transport layer."""
    
    name: str
    max_connections: int = 10
    timeout: float = 30.0
    buffer_size: int = 8192
    security_token: Optional[str] = None


class BaseTransport(ABC):
    """Abstract base class for transport implementations."""
    
    def __init__(self, config: TransportConfig):
        self.config = config
        self.is_server = False
        self.is_connected = False
        self._cleanup_callbacks: list[Callable] = []
    
    @abstractmethod
    async def start_server(self) -> str:
        """Start server and return connection address."""
        pass
    
    @abstractmethod
    async def connect(self, address: str) -> None:
        """Connect to server at address.""" 
        pass
    
    @abstractmethod
    async def send(self, data: bytes) -> None:
        """Send data."""
        pass
    
    @abstractmethod
    async def receive(self) -> bytes:
        """Receive data."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close connection."""
        pass
    
    def add_cleanup_callback(self, callback: Callable):
        """Add cleanup callback."""
        self._cleanup_callbacks.append(callback)
    
    async def cleanup(self):
        """Run cleanup callbacks."""
        for callback in self._cleanup_callbacks:
            try:
                await callback()
            except Exception as e:
                logger.warning(f"Cleanup callback error: {e}")


class UnixSocketTransport(BaseTransport):
    """Unix socket transport for Unix-like systems."""
    
    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self.socket_path: Optional[str] = None
        self.server: Optional[asyncio.Server] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connections: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        
    @handle_exception
    async def start_server(self) -> str:
        """Start Unix socket server."""
        # Create socket in temp directory
        temp_dir = Path(tempfile.gettempdir()) / "pyelectron"
        temp_dir.mkdir(exist_ok=True, mode=0o700)  # Secure permissions
        
        self.socket_path = str(temp_dir / f"{self.config.name}_{uuid.uuid4().hex[:8]}.sock")
        
        # Remove existing socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            """Handle new client connection."""
            client_id = str(uuid.uuid4())
            self.connections[client_id] = (reader, writer)
            
            try:
                logger.debug(f"Client connected: {client_id}")
                # Keep connection alive for client to use
                peer = writer.get_extra_info('peername')
                logger.debug(f"Client peer info: {peer}")
                
            except Exception as e:
                logger.error(f"Error handling client {client_id}: {e}")
            finally:
                if client_id in self.connections:
                    del self.connections[client_id]
                    
                writer.close()
                await writer.wait_closed()
                logger.debug(f"Client disconnected: {client_id}")
        
        # Start server
        self.server = await asyncio.start_unix_server(
            handle_client,
            path=self.socket_path
        )
        
        # Set secure permissions
        os.chmod(self.socket_path, 0o600)
        
        self.is_server = True
        self.is_connected = True
        
        # Add cleanup for socket file
        self.add_cleanup_callback(self._cleanup_socket)
        
        logger.info(f"Unix socket server started: {self.socket_path}")
        return self.socket_path
    
    @handle_exception
    async def connect(self, address: str) -> None:
        """Connect to Unix socket server."""
        if not os.path.exists(address):
            raise IPCError(f"Socket file does not exist: {address}")
        
        try:
            self.reader, self.writer = await asyncio.open_unix_connection(address)
            self.is_connected = True
            logger.info(f"Connected to Unix socket: {address}")
            
        except Exception as e:
            raise IPCError(f"Failed to connect to {address}: {str(e)}") from e
    
    @handle_exception
    async def send(self, data: bytes) -> None:
        """Send data over Unix socket."""
        if not self.is_connected or not self.writer:
            raise IPCError("Not connected")
        
        try:
            # Send length-prefixed message
            length = len(data)
            self.writer.write(length.to_bytes(4, byteorder='big'))
            self.writer.write(data)
            await self.writer.drain()
            
        except Exception as e:
            raise IPCError(f"Send failed: {str(e)}") from e
    
    @handle_exception
    async def receive(self) -> bytes:
        """Receive data from Unix socket."""
        if not self.is_connected or not self.reader:
            raise IPCError("Not connected")
        
        try:
            # Read length prefix
            length_bytes = await self.reader.readexactly(4)
            length = int.from_bytes(length_bytes, byteorder='big')
            
            if length > self.config.buffer_size * 10:  # Safety limit
                raise IPCError(f"Message too large: {length} bytes")
            
            # Read message data
            data = await self.reader.readexactly(length)
            return data
            
        except asyncio.IncompleteReadError as e:
            raise IPCError("Connection closed by peer") from e
        except Exception as e:
            raise IPCError(f"Receive failed: {str(e)}") from e
    
    async def _cleanup_socket(self):
        """Cleanup socket file."""
        if self.socket_path and os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
                logger.debug(f"Cleaned up socket file: {self.socket_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup socket file: {e}")
    
    async def close(self) -> None:
        """Close Unix socket connection."""
        self.is_connected = False
        
        # Close client connections
        for client_id, (reader, writer) in list(self.connections.items()):
            writer.close()
            await writer.wait_closed()
        self.connections.clear()
        
        # Close client connection
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        
        await self.cleanup()
        logger.debug("Unix socket transport closed")


class NamedPipeTransport(BaseTransport):
    """Named pipe transport for Windows."""
    
    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self.pipe_name: Optional[str] = None
        self.pipe_handle: Optional[Any] = None
        self._server_task: Optional[asyncio.Task] = None
    
    @handle_exception 
    async def start_server(self) -> str:
        """Start named pipe server."""
        import win32pipe
        import win32file
        import win32api
        
        # Generate unique pipe name
        pipe_id = uuid.uuid4().hex[:8]
        self.pipe_name = f"\\\\.\\pipe\\pyelectron_{self.config.name}_{pipe_id}"
        
        try:
            # Create named pipe
            self.pipe_handle = win32pipe.CreateNamedPipe(
                self.pipe_name,
                win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                self.config.max_connections,
                self.config.buffer_size,
                self.config.buffer_size,
                0,  # Default timeout
                None  # Default security
            )
            
            if self.pipe_handle == win32file.INVALID_HANDLE_VALUE:
                raise IPCError("Failed to create named pipe")
            
            self.is_server = True
            self.is_connected = True
            
            logger.info(f"Named pipe server started: {self.pipe_name}")
            return self.pipe_name
            
        except Exception as e:
            raise IPCError(f"Failed to start named pipe server: {str(e)}") from e
    
    @handle_exception
    async def connect(self, address: str) -> None:
        """Connect to named pipe server."""
        import win32file
        
        try:
            self.pipe_handle = win32file.CreateFile(
                address,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,  # No sharing
                None,  # Default security
                win32file.OPEN_EXISTING,
                win32file.FILE_FLAG_OVERLAPPED,
                None
            )
            
            if self.pipe_handle == win32file.INVALID_HANDLE_VALUE:
                raise IPCError(f"Failed to connect to named pipe: {address}")
            
            self.is_connected = True
            logger.info(f"Connected to named pipe: {address}")
            
        except Exception as e:
            raise IPCError(f"Failed to connect to {address}: {str(e)}") from e
    
    @handle_exception
    async def send(self, data: bytes) -> None:
        """Send data over named pipe."""
        if not self.is_connected or not self.pipe_handle:
            raise IPCError("Not connected")
        
        import win32file
        
        try:
            # Send length-prefixed message
            length = len(data)
            length_bytes = length.to_bytes(4, byteorder='big')
            
            # Write length prefix
            win32file.WriteFile(self.pipe_handle, length_bytes)
            
            # Write message data
            win32file.WriteFile(self.pipe_handle, data)
            
        except Exception as e:
            raise IPCError(f"Send failed: {str(e)}") from e
    
    @handle_exception
    async def receive(self) -> bytes:
        """Receive data from named pipe."""
        if not self.is_connected or not self.pipe_handle:
            raise IPCError("Not connected")
        
        import win32file
        
        try:
            # Read length prefix
            _, length_bytes = win32file.ReadFile(self.pipe_handle, 4)
            length = int.from_bytes(length_bytes, byteorder='big')
            
            if length > self.config.buffer_size * 10:  # Safety limit
                raise IPCError(f"Message too large: {length} bytes")
            
            # Read message data
            _, data = win32file.ReadFile(self.pipe_handle, length)
            return data
            
        except Exception as e:
            raise IPCError(f"Receive failed: {str(e)}") from e
    
    async def close(self) -> None:
        """Close named pipe connection."""
        if self.pipe_handle:
            import win32api
            try:
                win32api.CloseHandle(self.pipe_handle)
            except Exception as e:
                logger.warning(f"Error closing pipe handle: {e}")
            
            self.pipe_handle = None
        
        self.is_connected = False
        await self.cleanup()
        logger.debug("Named pipe transport closed")


class NativeTransport:
    """Factory for platform-specific transport."""
    
    @staticmethod
    def create(config: TransportConfig) -> BaseTransport:
        """Create appropriate transport for current platform."""
        system = platform.system()
        
        if system in ('Linux', 'Darwin'):  # Unix-like systems
            return UnixSocketTransport(config)
        elif system == 'Windows':
            return NamedPipeTransport(config)
        else:
            raise IPCError(f"Unsupported platform for IPC: {system}")
    
    @staticmethod
    def get_default_config(name: str) -> TransportConfig:
        """Get default transport configuration."""
        return TransportConfig(
            name=name,
            max_connections=10,
            timeout=30.0,
            buffer_size=8192,
            security_token=str(uuid.uuid4())
        )