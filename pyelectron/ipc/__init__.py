"""
PyElectron IPC (Inter-Process Communication)

This package provides secure JSON-RPC based communication between processes
using platform-native transport mechanisms (Unix sockets/named pipes).
"""

from .transport import NativeTransport, TransportConfig
from .protocol import JSONRPCProtocol, rpc_method
from .manager import IPCManager, create_ipc_manager
from .security import IPCSecurity, SecurityConfig, create_secure_config
from .router import ServiceRegistry, MessageRouter, BaseService, service_method

__all__ = [
    'NativeTransport',
    'TransportConfig', 
    'JSONRPCProtocol',
    'rpc_method',
    'IPCManager',
    'create_ipc_manager',
    'IPCSecurity',
    'SecurityConfig',
    'create_secure_config',
    'ServiceRegistry',
    'MessageRouter',
    'BaseService',
    'service_method',
]