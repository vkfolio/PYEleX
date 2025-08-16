"""
PyElectron IPC Security Layer

This module provides security measures for IPC communication including
input validation, rate limiting, and token-based authentication.
"""

import hashlib
import hmac
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Union

from pyelectron.utils.errors import SecurityError, ValidationError
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SecurityConfig:
    """Security configuration for IPC."""
    
    # Rate limiting
    max_requests_per_minute: int = 100
    max_payload_size: int = 1024 * 1024  # 1MB
    
    # Authentication
    require_auth_token: bool = True
    auth_token: Optional[str] = None
    
    # Method restrictions
    allowed_methods: Optional[Set[str]] = None
    blocked_methods: Set[str] = None
    
    # Input validation
    validate_json_structure: bool = True
    max_string_length: int = 10000
    max_array_length: int = 1000
    max_object_depth: int = 10


class RateLimiter:
    """Simple rate limiter for IPC requests."""
    
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def check_rate_limit(self, client_id: str) -> bool:
        """
        Check if client is within rate limits.
        
        Args:
            client_id: Client identifier
            
        Returns:
            bool: True if within limits
        """
        now = time.time()
        client_requests = self.requests[client_id]
        
        # Remove old requests outside window
        while client_requests and client_requests[0] < now - self.window_seconds:
            client_requests.popleft()
        
        # Check if under limit
        if len(client_requests) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            return False
        
        # Add current request
        client_requests.append(now)
        return True
    
    def cleanup_old_entries(self):
        """Remove old rate limit entries."""
        now = time.time()
        
        for client_id in list(self.requests.keys()):
            client_requests = self.requests[client_id]
            
            # Remove old requests
            while client_requests and client_requests[0] < now - self.window_seconds:
                client_requests.popleft()
            
            # Remove empty deques
            if not client_requests:
                del self.requests[client_id]


class InputValidator:
    """Validates JSON-RPC input for security."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
    
    def validate_message_size(self, data: str) -> None:
        """Validate message size."""
        if len(data.encode('utf-8')) > self.config.max_payload_size:
            raise SecurityError(
                f"Message too large: {len(data)} bytes > {self.config.max_payload_size}"
            )
    
    def validate_json_structure(self, data: Any, depth: int = 0) -> None:
        """
        Recursively validate JSON structure for security.
        
        Args:
            data: JSON data to validate
            depth: Current recursion depth
        """
        if depth > self.config.max_object_depth:
            raise SecurityError(f"JSON structure too deep: {depth} > {self.config.max_object_depth}")
        
        if isinstance(data, str):
            if len(data) > self.config.max_string_length:
                raise SecurityError(f"String too long: {len(data)} > {self.config.max_string_length}")
        
        elif isinstance(data, list):
            if len(data) > self.config.max_array_length:
                raise SecurityError(f"Array too long: {len(data)} > {self.config.max_array_length}")
            
            for item in data:
                self.validate_json_structure(item, depth + 1)
        
        elif isinstance(data, dict):
            for key, value in data.items():
                if not isinstance(key, str):
                    raise SecurityError("Object keys must be strings")
                
                if len(key) > self.config.max_string_length:
                    raise SecurityError(f"Object key too long: {len(key)}")
                
                self.validate_json_structure(value, depth + 1)
    
    def validate_method_name(self, method: str) -> None:
        """Validate method name against allow/block lists."""
        if self.config.blocked_methods and method in self.config.blocked_methods:
            raise SecurityError(f"Method blocked: {method}")
        
        if self.config.allowed_methods and method not in self.config.allowed_methods:
            raise SecurityError(f"Method not allowed: {method}")
        
        # Check for dangerous method patterns
        dangerous_patterns = [
            '__',  # Python internal methods
            'exec',
            'eval',
            'import',
            'open',
            'file',
            'system',
        ]
        
        method_lower = method.lower()
        for pattern in dangerous_patterns:
            if pattern in method_lower:
                raise SecurityError(f"Potentially dangerous method name: {method}")
    
    def validate_parameters(self, params: Any) -> None:
        """Validate method parameters."""
        if params is not None:
            self.validate_json_structure(params)
            
            # Additional parameter-specific validation
            if isinstance(params, dict):
                # Check for dangerous parameter names
                dangerous_keys = ['__class__', '__module__', '__globals__', 'func_code']
                for key in params:
                    if key in dangerous_keys:
                        raise SecurityError(f"Dangerous parameter name: {key}")


class TokenAuthenticator:
    """Token-based authentication for IPC."""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode('utf-8')
    
    def generate_token(self, payload: Dict[str, Any]) -> str:
        """Generate authentication token."""
        # Add timestamp to payload
        payload_with_time = {
            **payload,
            'timestamp': int(time.time())
        }
        
        # Create JSON payload
        json_payload = json.dumps(payload_with_time, sort_keys=True, separators=(',', ':'))
        
        # Generate HMAC signature
        signature = hmac.new(
            self.secret_key,
            json_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"{json_payload}|{signature}"
    
    def verify_token(self, token: str, max_age_seconds: int = 3600) -> Dict[str, Any]:
        """
        Verify authentication token.
        
        Args:
            token: Token to verify
            max_age_seconds: Maximum token age
            
        Returns:
            Dict: Token payload if valid
            
        Raises:
            SecurityError: If token is invalid
        """
        try:
            # Split payload and signature
            if '|' not in token:
                raise SecurityError("Invalid token format")
            
            json_payload, signature = token.rsplit('|', 1)
            
            # Verify signature
            expected_signature = hmac.new(
                self.secret_key,
                json_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                raise SecurityError("Invalid token signature")
            
            # Parse payload
            payload = json.loads(json_payload)
            
            # Check timestamp
            if 'timestamp' not in payload:
                raise SecurityError("Token missing timestamp")
            
            token_age = int(time.time()) - payload['timestamp']
            if token_age > max_age_seconds:
                raise SecurityError(f"Token expired: {token_age}s > {max_age_seconds}s")
            
            return payload
            
        except json.JSONDecodeError as e:
            raise SecurityError(f"Invalid token payload: {str(e)}") from e
        except Exception as e:
            raise SecurityError(f"Token verification failed: {str(e)}") from e


class IPCSecurity:
    """Main security manager for IPC communications."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.rate_limiter = RateLimiter(config.max_requests_per_minute)
        self.validator = InputValidator(config)
        self.authenticator = TokenAuthenticator(config.auth_token) if config.auth_token else None
        
        logger.debug("IPCSecurity initialized")
    
    def validate_incoming_message(self, message: str, client_id: str, 
                                 auth_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate incoming IPC message for security.
        
        Args:
            message: Raw message content
            client_id: Client identifier
            auth_token: Authentication token
            
        Returns:
            Dict: Parsed and validated message
            
        Raises:
            SecurityError: If validation fails
        """
        # Check rate limits
        if not self.rate_limiter.check_rate_limit(client_id):
            raise SecurityError("Rate limit exceeded")
        
        # Validate message size
        self.validator.validate_message_size(message)
        
        # Parse JSON
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {str(e)}") from e
        
        # Validate JSON structure
        if self.config.validate_json_structure:
            self.validator.validate_json_structure(data)
        
        # Authenticate if required
        if self.config.require_auth_token and self.authenticator:
            if not auth_token:
                raise SecurityError("Authentication token required")
            
            # Verify token
            self.authenticator.verify_token(auth_token)
        
        # Validate method if this is a request
        if 'method' in data:
            method = data['method']
            if not isinstance(method, str):
                raise ValidationError("Method must be a string")
            
            self.validator.validate_method_name(method)
            
            # Validate parameters
            if 'params' in data:
                self.validator.validate_parameters(data['params'])
        
        return data
    
    def generate_auth_token(self, client_id: str, permissions: Optional[list] = None) -> str:
        """Generate authentication token for client."""
        if not self.authenticator:
            raise SecurityError("Authentication not configured")
        
        payload = {
            'client_id': client_id,
            'permissions': permissions or []
        }
        
        return self.authenticator.generate_token(payload)
    
    def cleanup(self):
        """Cleanup security resources."""
        self.rate_limiter.cleanup_old_entries()
        logger.debug("IPCSecurity cleaned up")


def create_secure_config(auth_token: str, **kwargs) -> SecurityConfig:
    """Create secure configuration with reasonable defaults."""
    return SecurityConfig(
        auth_token=auth_token,
        max_requests_per_minute=100,
        max_payload_size=1024 * 1024,  # 1MB
        require_auth_token=True,
        validate_json_structure=True,
        max_string_length=10000,
        max_array_length=1000,
        max_object_depth=10,
        blocked_methods={
            '__import__',
            'exec',
            'eval',
            'compile',
            'open',
            '__builtins__',
        },
        **kwargs
    )