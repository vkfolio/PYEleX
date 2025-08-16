"""
Inter-Process Communication (IPC) modules

This package provides secure and efficient communication between
PyElectron processes using JSON-RPC over native transports.
"""

from pyelectron.ipc.jsonrpc import JSONRPCHandler, JSONRPCClient
from pyelectron.ipc.transport import NativeTransport
from pyelectron.ipc.shared_memory import SharedDataManager

__all__ = [
    "JSONRPCHandler",
    "JSONRPCClient", 
    "NativeTransport",
    "SharedDataManager",
]