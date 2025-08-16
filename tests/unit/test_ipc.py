"""
Unit tests for PyElectron IPC system

Tests the complete IPC stack including transport, protocol, security,
and management layers.
"""

import asyncio
import json
import os
import platform
import tempfile
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyelectron.ipc import (
    NativeTransport,
    TransportConfig,
    JSONRPCProtocol,
    rpc_method,
    IPCManager,
    create_ipc_manager,
    IPCSecurity,
    SecurityConfig,
    create_secure_config,
    ServiceRegistry,
    MessageRouter,
    BaseService,
    service_method,
)
from pyelectron.ipc.transport import UnixSocketTransport, NamedPipeTransport
from pyelectron.ipc.protocol import RPCErrorCode, RPCMessage, RPCRequest, RPCResponse
from pyelectron.ipc.security import RateLimiter, InputValidator, TokenAuthenticator
from pyelectron.ipc.router import MethodInfo, requires_auth, requires_permissions
from pyelectron.utils.errors import IPCError, RPCError, SecurityError, ValidationError


class TestTransportConfig:
    """Test TransportConfig data class."""
    
    def test_transport_config_basic(self):
        """Test basic TransportConfig creation."""
        config = TransportConfig(name="test")
        
        assert config.name == "test"
        assert config.max_connections == 10
        assert config.timeout == 30.0
        assert config.buffer_size == 8192
        assert config.security_token is None
    
    def test_transport_config_custom(self):
        """Test TransportConfig with custom values."""
        config = TransportConfig(
            name="custom",
            max_connections=5,
            timeout=60.0,
            buffer_size=4096,
            security_token="secret"
        )
        
        assert config.name == "custom"
        assert config.max_connections == 5
        assert config.timeout == 60.0
        assert config.buffer_size == 4096
        assert config.security_token == "secret"


class TestNativeTransport:
    """Test NativeTransport factory."""
    
    def test_create_unix_transport(self):
        """Test creating Unix socket transport."""
        config = TransportConfig(name="test")
        
        with patch('platform.system', return_value='Linux'):
            transport = NativeTransport.create(config)
            assert isinstance(transport, UnixSocketTransport)
    
    def test_create_windows_transport(self):
        """Test creating Windows named pipe transport."""
        config = TransportConfig(name="test")
        
        with patch('platform.system', return_value='Windows'):
            transport = NativeTransport.create(config)
            assert isinstance(transport, NamedPipeTransport)
    
    def test_unsupported_platform(self):
        """Test error on unsupported platform."""
        config = TransportConfig(name="test")
        
        with patch('platform.system', return_value='Unsupported'):
            with pytest.raises(IPCError) as exc_info:
                NativeTransport.create(config)
            
            assert "Unsupported platform" in str(exc_info.value)
    
    def test_get_default_config(self):
        """Test default config generation."""
        config = NativeTransport.get_default_config("test")
        
        assert config.name == "test"
        assert config.max_connections == 10
        assert config.security_token is not None


@pytest.mark.skipif(platform.system() == 'Windows', reason="Unix socket tests")
class TestUnixSocketTransport:
    """Test Unix socket transport."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = TransportConfig(name="test_socket")
        self.transport = UnixSocketTransport(self.config)
    
    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'transport'):
            asyncio.run(self.transport.close())
    
    @pytest.mark.asyncio
    async def test_server_start_stop(self):
        """Test starting and stopping Unix socket server."""
        # Start server
        address = await self.transport.start_server()
        
        assert self.transport.is_server
        assert self.transport.is_connected
        assert os.path.exists(address)
        assert address.endswith('.sock')
        
        # Stop server
        await self.transport.close()
        assert not self.transport.is_connected
    
    @pytest.mark.asyncio
    async def test_client_connection(self):
        """Test client connection to Unix socket."""
        # Start server
        server_transport = UnixSocketTransport(self.config)
        address = await server_transport.start_server()
        
        try:
            # Connect client
            client_transport = UnixSocketTransport(self.config)
            await client_transport.connect(address)
            
            assert client_transport.is_connected
            assert not client_transport.is_server
            
            await client_transport.close()
            
        finally:
            await server_transport.close()
    
    @pytest.mark.asyncio
    async def test_connect_nonexistent_socket(self):
        """Test connecting to non-existent socket."""
        with pytest.raises(IPCError) as exc_info:
            await self.transport.connect("/nonexistent/socket.sock")
        
        assert "does not exist" in str(exc_info.value)


class TestJSONRPCProtocol:
    """Test JSON-RPC protocol implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.protocol = JSONRPCProtocol()
    
    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'protocol'):
            self.protocol.cleanup()
    
    def test_create_request(self):
        """Test creating JSON-RPC request."""
        request = self.protocol.create_request("test_method", {"param": "value"}, "123")
        data = json.loads(request)
        
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "test_method"
        assert data["params"] == {"param": "value"}
        assert data["id"] == "123"
    
    def test_create_notification(self):
        """Test creating JSON-RPC notification."""
        notification = self.protocol.create_notification("test_method", ["arg1", "arg2"])
        data = json.loads(notification)
        
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "test_method"
        assert data["params"] == ["arg1", "arg2"]
        assert "id" not in data
    
    def test_create_response(self):
        """Test creating JSON-RPC response."""
        response = self.protocol.create_response("123", {"result": "success"})
        data = json.loads(response)
        
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "123"
        assert data["result"] == {"result": "success"}
    
    def test_create_error_response(self):
        """Test creating JSON-RPC error response."""
        response = self.protocol.create_error_response(
            "123", 
            RPCErrorCode.METHOD_NOT_FOUND, 
            "Method not found"
        )
        data = json.loads(response)
        
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "123"
        assert data["error"]["code"] == -32601
        assert data["error"]["message"] == "Method not found"
    
    def test_register_method(self):
        """Test registering RPC method."""
        def test_handler():
            return "success"
        
        self.protocol.register_method("test", test_handler)
        assert "test" in self.protocol.methods
        assert self.protocol.methods["test"] == test_handler
    
    @pytest.mark.asyncio
    async def test_process_valid_request(self):
        """Test processing valid JSON-RPC request."""
        def test_handler():
            return "success"
        
        self.protocol.register_method("test", test_handler)
        
        request = self.protocol.create_request("test", None, "123")
        response_json = await self.protocol.process_message(request)
        
        response = json.loads(response_json)
        assert response["id"] == "123"
        assert response["result"] == "success"
    
    @pytest.mark.asyncio
    async def test_process_method_not_found(self):
        """Test processing request for non-existent method."""
        request = self.protocol.create_request("nonexistent", None, "123")
        response_json = await self.protocol.process_message(request)
        
        response = json.loads(response_json)
        assert response["id"] == "123"
        assert response["error"]["code"] == -32601
        assert "not found" in response["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_process_invalid_json(self):
        """Test processing invalid JSON."""
        response_json = await self.protocol.process_message("invalid json")
        
        response = json.loads(response_json)
        assert response["error"]["code"] == -32700
        assert "Parse error" in response["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_process_notification(self):
        """Test processing notification (no response)."""
        def test_handler():
            return "success"
        
        self.protocol.register_method("test", test_handler)
        
        notification = self.protocol.create_notification("test", None)
        response = await self.protocol.process_message(notification)
        
        assert response is None  # No response for notifications


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_rate_limiter_allows_requests(self):
        """Test rate limiter allows requests within limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        # Should allow 5 requests
        for i in range(5):
            assert limiter.check_rate_limit("client1")
    
    def test_rate_limiter_blocks_excess(self):
        """Test rate limiter blocks excess requests."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        # Allow first 2 requests
        assert limiter.check_rate_limit("client1")
        assert limiter.check_rate_limit("client1")
        
        # Block 3rd request
        assert not limiter.check_rate_limit("client1")
    
    def test_rate_limiter_per_client(self):
        """Test rate limiter works per client."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        # Client 1 uses up limit
        assert limiter.check_rate_limit("client1")
        assert limiter.check_rate_limit("client1")
        assert not limiter.check_rate_limit("client1")
        
        # Client 2 should still be allowed
        assert limiter.check_rate_limit("client2")
        assert limiter.check_rate_limit("client2")
    
    def test_rate_limiter_window_reset(self):
        """Test rate limiter window reset."""
        limiter = RateLimiter(max_requests=1, window_seconds=1)
        
        # Use up limit
        assert limiter.check_rate_limit("client1")
        assert not limiter.check_rate_limit("client1")
        
        # Wait for window to pass
        time.sleep(1.1)
        
        # Should be allowed again
        assert limiter.check_rate_limit("client1")


class TestInputValidator:
    """Test input validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SecurityConfig()
        self.validator = InputValidator(self.config)
    
    def test_validate_message_size_ok(self):
        """Test message size validation passes."""
        small_message = "small message"
        # Should not raise
        self.validator.validate_message_size(small_message)
    
    def test_validate_message_size_too_large(self):
        """Test message size validation fails for large messages."""
        large_message = "x" * (self.config.max_payload_size + 1)
        
        with pytest.raises(SecurityError) as exc_info:
            self.validator.validate_message_size(large_message)
        
        assert "too large" in str(exc_info.value)
    
    def test_validate_json_structure_ok(self):
        """Test JSON structure validation passes."""
        valid_data = {
            "method": "test",
            "params": {"key": "value"},
            "array": [1, 2, 3]
        }
        
        # Should not raise
        self.validator.validate_json_structure(valid_data)
    
    def test_validate_json_structure_too_deep(self):
        """Test JSON structure validation fails for deep nesting."""
        # Create deeply nested object
        deep_data = {}
        current = deep_data
        for i in range(self.config.max_object_depth + 1):
            current["nested"] = {}
            current = current["nested"]
        
        with pytest.raises(SecurityError) as exc_info:
            self.validator.validate_json_structure(deep_data)
        
        assert "too deep" in str(exc_info.value)
    
    def test_validate_method_name_ok(self):
        """Test method name validation passes."""
        # Should not raise
        self.validator.validate_method_name("valid_method")
    
    def test_validate_method_name_dangerous(self):
        """Test method name validation blocks dangerous names."""
        dangerous_names = ["__import__", "exec", "eval", "system"]
        
        for name in dangerous_names:
            with pytest.raises(SecurityError):
                self.validator.validate_method_name(name)


class TestTokenAuthenticator:
    """Test token-based authentication."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.auth = TokenAuthenticator("test_secret_key")
    
    def test_generate_and_verify_token(self):
        """Test token generation and verification."""
        payload = {"user": "test", "permissions": ["read"]}
        
        # Generate token
        token = self.auth.generate_token(payload)
        assert isinstance(token, str)
        assert "|" in token
        
        # Verify token
        verified_payload = self.auth.verify_token(token)
        assert verified_payload["user"] == "test"
        assert verified_payload["permissions"] == ["read"]
        assert "timestamp" in verified_payload
    
    def test_verify_invalid_token(self):
        """Test verification of invalid token."""
        with pytest.raises(SecurityError):
            self.auth.verify_token("invalid_token")
    
    def test_verify_tampered_token(self):
        """Test verification of tampered token."""
        payload = {"user": "test"}
        token = self.auth.generate_token(payload)
        
        # Tamper with token
        tampered_token = token.replace("test", "admin")
        
        with pytest.raises(SecurityError):
            self.auth.verify_token(tampered_token)
    
    def test_verify_expired_token(self):
        """Test verification of expired token."""
        payload = {"user": "test"}
        token = self.auth.generate_token(payload)
        
        # Should fail with very short max age
        with pytest.raises(SecurityError) as exc_info:
            self.auth.verify_token(token, max_age_seconds=0)
        
        assert "expired" in str(exc_info.value)


class TestServiceRegistry:
    """Test service registry functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.registry = ServiceRegistry()
    
    def test_register_method(self):
        """Test registering individual method."""
        def test_handler():
            return "success"
        
        self.registry.register_method("test", test_handler)
        
        method_info = self.registry.get_method("test")
        assert method_info is not None
        assert method_info.name == "test"
        assert method_info.handler == test_handler
    
    def test_register_service_object(self):
        """Test registering service object."""
        class TestService(BaseService):
            @service_method("custom_ping")
            def custom_ping(self):
                return "custom_pong"
        
        service = TestService("test_service")
        self.registry.register_service("test_service", service)
        
        # Check if methods were registered
        methods = self.registry.list_methods("test_service")
        assert "ping" in methods
        assert "custom_ping" in methods
        assert "get_service_info" in methods
    
    def test_unregister_service(self):
        """Test unregistering service."""
        self.registry.register_method("test1", lambda: None, "service1")
        self.registry.register_method("test2", lambda: None, "service1")
        
        assert len(self.registry.list_methods("service1")) == 2
        
        self.registry.unregister_service("service1")
        assert len(self.registry.list_methods("service1")) == 0
    
    def test_list_services(self):
        """Test listing services."""
        self.registry.register_method("test1", lambda: None, "service1")
        self.registry.register_method("test2", lambda: None, "service2")
        
        services = self.registry.list_services()
        assert "service1" in services
        assert "service2" in services


class TestMessageRouter:
    """Test message routing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.registry = ServiceRegistry()
        self.router = MessageRouter(self.registry)
    
    @pytest.mark.asyncio
    async def test_route_simple_method(self):
        """Test routing simple method call."""
        def test_handler():
            return "success"
        
        self.registry.register_method("test", test_handler)
        
        result = await self.router.route_message("test", None)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_route_method_with_params(self):
        """Test routing method with parameters."""
        def test_handler(a, b):
            return a + b
        
        self.registry.register_method("add", test_handler)
        
        result = await self.router.route_message("add", [5, 3])
        assert result == 8
    
    @pytest.mark.asyncio
    async def test_route_method_not_found(self):
        """Test routing non-existent method."""
        with pytest.raises(RPCError) as exc_info:
            await self.router.route_message("nonexistent", None)
        
        assert "not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_route_with_middleware(self):
        """Test routing with middleware."""
        middleware_calls = []
        
        async def request_middleware(method, params, context):
            middleware_calls.append(("request", method))
        
        async def response_middleware(method, result, context):
            middleware_calls.append(("response", method))
        
        self.router.add_request_middleware(request_middleware)
        self.router.add_response_middleware(response_middleware)
        
        def test_handler():
            return "success"
        
        self.registry.register_method("test", test_handler)
        
        result = await self.router.route_message("test", None)
        
        assert result == "success"
        assert ("request", "test") in middleware_calls
        assert ("response", "test") in middleware_calls


@pytest.mark.asyncio
class TestIPCManager:
    """Test IPC manager integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = None
    
    def teardown_method(self):
        """Clean up after tests."""
        if self.manager:
            asyncio.run(self.manager.shutdown())
    
    async def test_create_manager(self):
        """Test creating IPC manager."""
        self.manager = create_ipc_manager("test_manager")
        
        assert self.manager.name == "test_manager"
        assert not self.manager.is_server
        assert not self.manager.is_connected
    
    async def test_register_and_call_method(self):
        """Test registering and calling methods."""
        self.manager = create_ipc_manager("test_manager")
        
        def test_handler():
            return "success"
        
        self.manager.register_method("test", test_handler)
        
        # Check method was registered
        assert "test" in self.manager.protocol.methods
    
    @pytest.mark.skipif(platform.system() == 'Windows', reason="Unix socket test")
    async def test_start_server(self):
        """Test starting IPC server."""
        self.manager = create_ipc_manager("test_server")
        
        address = await self.manager.start_server()
        
        assert self.manager.is_server
        assert self.manager.is_connected
        assert address.endswith('.sock')
        assert os.path.exists(address)


class TestSecurityIntegration:
    """Test security integration."""
    
    def test_create_secure_config(self):
        """Test creating secure configuration."""
        config = create_secure_config("test_token")
        
        assert config.auth_token == "test_token"
        assert config.require_auth_token is True
        assert config.validate_json_structure is True
        assert "__import__" in config.blocked_methods
    
    def test_security_validation(self):
        """Test security validation."""
        config = create_secure_config("test_token")
        security = IPCSecurity(config)
        
        # Valid message should pass
        valid_message = json.dumps({
            "jsonrpc": "2.0",
            "method": "test",
            "id": "123"
        })
        
        # This would require proper token in real scenario
        # For test, we'll disable auth requirement
        config.require_auth_token = False
        
        # Should not raise
        data = security.validate_incoming_message(valid_message, "client1")
        assert data["method"] == "test"


class TestRPCDecorators:
    """Test RPC decorators."""
    
    def test_rpc_method_decorator(self):
        """Test @rpc_method decorator."""
        @rpc_method("custom_name")
        def test_function():
            return "success"
        
        assert hasattr(test_function, '_rpc_method_name')
        assert test_function._rpc_method_name == "custom_name"
    
    def test_service_method_decorator(self):
        """Test @service_method decorator."""
        @service_method("test_service", "Test method")
        def test_function():
            return "success"
        
        assert hasattr(test_function, '_rpc_method_name')
        assert test_function._rpc_method_name == "test_service"
    
    def test_requires_auth_decorator(self):
        """Test @requires_auth decorator."""
        @requires_auth
        def test_function():
            return "success"
        
        assert hasattr(test_function, '_requires_auth')
        assert test_function._requires_auth is True
    
    def test_requires_permissions_decorator(self):
        """Test @requires_permissions decorator."""
        @requires_permissions("read", "write")
        def test_function():
            return "success"
        
        assert hasattr(test_function, '_permissions')
        assert test_function._permissions == ("read", "write")


@pytest.mark.integration 
class TestIPCIntegration:
    """Integration tests for complete IPC system."""
    
    @pytest.mark.skipif(platform.system() == 'Windows', reason="Unix socket test")
    @pytest.mark.asyncio
    async def test_full_ipc_workflow(self):
        """Test complete IPC workflow."""
        # Create server
        server_manager = create_ipc_manager("integration_server")
        
        def echo_handler(message):
            return f"Echo: {message}"
        
        server_manager.register_method("echo", echo_handler)
        
        try:
            # Start server
            address = await server_manager.start_server()
            
            # Give server time to start
            await asyncio.sleep(0.1)
            
            # Create client
            client_manager = create_ipc_manager("integration_client")
            
            try:
                # Connect client
                await client_manager.connect_to_server(address)
                
                # Give connection time to establish
                await asyncio.sleep(0.1)
                
                # Test basic connectivity
                assert server_manager.is_server
                assert client_manager.is_connected
                
            finally:
                await client_manager.shutdown()
                
        finally:
            await server_manager.shutdown()