"""
PyElectron WebView Security Configuration

This module provides security configuration and policies for WebView instances,
ensuring safe web content rendering with appropriate restrictions.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Union
from urllib.parse import urlparse

from .base import SecurityPolicy, WebViewConfig
from pyelectron.utils.errors import SecurityError
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContentSecurityPolicy:
    """Content Security Policy configuration for WebView."""
    
    # Directive configurations
    default_src: List[str] = field(default_factory=lambda: ["'self'"])
    script_src: List[str] = field(default_factory=lambda: ["'self'"])
    style_src: List[str] = field(default_factory=lambda: ["'self'", "'unsafe-inline'"])
    img_src: List[str] = field(default_factory=lambda: ["'self'", "data:", "https:"])
    font_src: List[str] = field(default_factory=lambda: ["'self'", "https:"])
    connect_src: List[str] = field(default_factory=lambda: ["'self'"])
    media_src: List[str] = field(default_factory=lambda: ["'self'"])
    object_src: List[str] = field(default_factory=lambda: ["'none'"])
    frame_src: List[str] = field(default_factory=lambda: ["'none'"])
    worker_src: List[str] = field(default_factory=lambda: ["'self'"])
    
    # Security directives
    upgrade_insecure_requests: bool = True
    block_all_mixed_content: bool = True
    
    def to_header_value(self) -> str:
        """Convert CSP to HTTP header value."""
        directives = []
        
        # Add source directives
        for directive, sources in [
            ('default-src', self.default_src),
            ('script-src', self.script_src),
            ('style-src', self.style_src),
            ('img-src', self.img_src),
            ('font-src', self.font_src),
            ('connect-src', self.connect_src),
            ('media-src', self.media_src),
            ('object-src', self.object_src),
            ('frame-src', self.frame_src),
            ('worker-src', self.worker_src),
        ]:
            if sources:
                directives.append(f"{directive} {' '.join(sources)}")
        
        # Add boolean directives
        if self.upgrade_insecure_requests:
            directives.append("upgrade-insecure-requests")
        
        if self.block_all_mixed_content:
            directives.append("block-all-mixed-content")
        
        return "; ".join(directives)


@dataclass
class WebViewSecurityConfig:
    """Comprehensive security configuration for WebView."""
    
    # Content Security Policy
    csp: ContentSecurityPolicy = field(default_factory=ContentSecurityPolicy)
    
    # URL filtering
    allowed_protocols: Set[str] = field(default_factory=lambda: {"https", "http", "file", "data"})
    blocked_protocols: Set[str] = field(default_factory=lambda: {"ftp", "javascript", "vbscript"})
    allowed_domains: Optional[Set[str]] = None
    blocked_domains: Set[str] = field(default_factory=set)
    
    # JavaScript security
    enable_javascript: bool = True
    enable_eval: bool = False
    enable_function_constructor: bool = False
    enable_wasm: bool = False
    
    # Plugin and extension security
    enable_plugins: bool = False
    enable_java: bool = False
    enable_flash: bool = False
    enable_extensions: bool = False
    
    # Network security
    enable_mixed_content: bool = False
    enable_insecure_requests: bool = False
    enable_cors: bool = True
    
    # Storage security
    enable_local_storage: bool = True
    enable_session_storage: bool = True
    enable_indexeddb: bool = True
    enable_websql: bool = False
    enable_cache: bool = True
    
    # Privacy settings
    enable_cookies: bool = True
    enable_third_party_cookies: bool = False
    enable_geolocation: bool = False
    enable_camera: bool = False
    enable_microphone: bool = False
    enable_notifications: bool = False
    
    # Development settings
    enable_dev_tools: bool = False
    enable_context_menu: bool = True
    enable_text_selection: bool = True
    enable_drag_drop: bool = True


class SecurityPolicyManager:
    """Manager for WebView security policies and configurations."""
    
    # Predefined security configurations
    SECURITY_CONFIGS = {
        SecurityPolicy.STRICT: WebViewSecurityConfig(
            csp=ContentSecurityPolicy(
                default_src=["'self'"],
                script_src=["'self'"],
                style_src=["'self'"],
                img_src=["'self'"],
                font_src=["'self'"],
                connect_src=["'self'"],
                object_src=["'none'"],
                frame_src=["'none'"],
            ),
            allowed_protocols={"https", "file"},
            enable_javascript=False,
            enable_plugins=False,
            enable_mixed_content=False,
            enable_third_party_cookies=False,
            enable_geolocation=False,
            enable_camera=False,
            enable_microphone=False,
            enable_dev_tools=False,
            enable_context_menu=False,
        ),
        
        SecurityPolicy.BALANCED: WebViewSecurityConfig(
            csp=ContentSecurityPolicy(
                default_src=["'self'"],
                script_src=["'self'", "'unsafe-inline'"],
                style_src=["'self'", "'unsafe-inline'"],
                img_src=["'self'", "data:", "https:"],
                font_src=["'self'", "https:"],
                connect_src=["'self'", "https:"],
            ),
            allowed_protocols={"https", "http", "file", "data"},
            enable_javascript=True,
            enable_eval=False,
            enable_plugins=False,
            enable_mixed_content=False,
            enable_third_party_cookies=False,
            enable_geolocation=False,
            enable_camera=False,
            enable_microphone=False,
        ),
        
        SecurityPolicy.PERMISSIVE: WebViewSecurityConfig(
            csp=ContentSecurityPolicy(
                default_src=["*"],
                script_src=["*", "'unsafe-inline'", "'unsafe-eval'"],
                style_src=["*", "'unsafe-inline'"],
                img_src=["*", "data:"],
                font_src=["*"],
                connect_src=["*"],
                frame_src=["*"],
            ),
            allowed_protocols={"https", "http", "file", "data", "blob"},
            enable_javascript=True,
            enable_eval=True,
            enable_plugins=True,
            enable_mixed_content=True,
            enable_third_party_cookies=True,
            enable_geolocation=True,
            enable_camera=True,
            enable_microphone=True,
            enable_dev_tools=True,
        ),
    }
    
    @classmethod
    def get_security_config(cls, policy: SecurityPolicy) -> WebViewSecurityConfig:
        """Get security configuration for a policy."""
        return cls.SECURITY_CONFIGS.get(policy, cls.SECURITY_CONFIGS[SecurityPolicy.BALANCED])
    
    @classmethod
    def validate_url(cls, url: str, config: WebViewSecurityConfig) -> bool:
        """Validate URL against security configuration."""
        try:
            parsed = urlparse(url)
            
            # Check protocol
            if parsed.scheme not in config.allowed_protocols:
                logger.warning(f"Blocked URL with disallowed protocol: {url}")
                return False
            
            if parsed.scheme in config.blocked_protocols:
                logger.warning(f"Blocked URL with blocked protocol: {url}")
                return False
            
            # Check domain restrictions
            if parsed.hostname:
                if config.allowed_domains and parsed.hostname not in config.allowed_domains:
                    logger.warning(f"Blocked URL with disallowed domain: {url}")
                    return False
                
                if parsed.hostname in config.blocked_domains:
                    logger.warning(f"Blocked URL with blocked domain: {url}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False
    
    @classmethod
    def generate_security_headers(cls, config: WebViewSecurityConfig) -> Dict[str, str]:
        """Generate HTTP security headers for WebView."""
        headers = {}
        
        # Content Security Policy
        headers['Content-Security-Policy'] = config.csp.to_header_value()
        
        # Additional security headers
        headers['X-Frame-Options'] = 'DENY'
        headers['X-Content-Type-Options'] = 'nosniff'
        headers['X-XSS-Protection'] = '1; mode=block'
        headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # HTTPS enforcement
        if not config.enable_insecure_requests:
            headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return headers
    
    @classmethod
    def create_secure_config(cls, base_policy: SecurityPolicy = SecurityPolicy.BALANCED,
                           **overrides) -> WebViewSecurityConfig:
        """Create a secure configuration with optional overrides."""
        config = cls.get_security_config(base_policy)
        
        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                logger.warning(f"Unknown security config option: {key}")
        
        return config


class URLValidator:
    """Utility class for URL validation and filtering."""
    
    # Dangerous URL patterns
    DANGEROUS_PATTERNS = [
        r'javascript:',
        r'vbscript:',
        r'data:text/html',
        r'file:///(?!.*\.(?:html|htm|css|js|png|jpg|jpeg|gif|svg)$)',
        r'about:(?!blank)',
    ]
    
    # Safe file extensions for file:// URLs
    SAFE_FILE_EXTENSIONS = {
        '.html', '.htm', '.css', '.js', '.json',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
        '.mp4', '.webm', '.ogg', '.mp3', '.wav',
        '.pdf', '.txt', '.md'
    }
    
    @classmethod
    def is_safe_url(cls, url: str) -> bool:
        """Check if URL is safe to load."""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # Check against dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, url_lower):
                logger.warning(f"Dangerous URL pattern detected: {url}")
                return False
        
        # Special handling for file:// URLs
        if url_lower.startswith('file://'):
            return cls._is_safe_file_url(url)
        
        return True
    
    @classmethod
    def _is_safe_file_url(cls, url: str) -> bool:
        """Check if file:// URL is safe."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            
            # Check file extension
            for ext in cls.SAFE_FILE_EXTENSIONS:
                if path.endswith(ext):
                    return True
            
            # Reject if no safe extension found
            logger.warning(f"Unsafe file URL (no safe extension): {url}")
            return False
            
        except Exception as e:
            logger.error(f"Error validating file URL {url}: {e}")
            return False
    
    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """Sanitize URL by removing dangerous components."""
        if not url:
            return ""
        
        # Remove null bytes and control characters
        url = re.sub(r'[\x00-\x1f\x7f]', '', url)
        
        # Normalize whitespace
        url = url.strip()
        
        return url


def create_development_config() -> WebViewSecurityConfig:
    """Create security config optimized for development."""
    return SecurityPolicyManager.create_secure_config(
        SecurityPolicy.BALANCED,
        enable_dev_tools=True,
        enable_mixed_content=True,
        enable_context_menu=True,
    )


def create_production_config() -> WebViewSecurityConfig:
    """Create security config optimized for production."""
    return SecurityPolicyManager.create_secure_config(
        SecurityPolicy.BALANCED,
        enable_dev_tools=False,
        enable_mixed_content=False,
        enable_third_party_cookies=False,
    )


def apply_security_config_to_webview_config(
    webview_config: WebViewConfig,
    security_config: WebViewSecurityConfig
) -> WebViewConfig:
    """Apply security configuration to WebView configuration."""
    
    # Update WebView config with security settings
    webview_config.security_policy = SecurityPolicy.BALANCED  # Will be refined by security_config
    webview_config.enable_javascript = security_config.enable_javascript
    webview_config.enable_plugins = security_config.enable_plugins
    webview_config.enable_dev_tools = security_config.enable_dev_tools
    webview_config.enable_context_menu = security_config.enable_context_menu
    
    # Set domain restrictions
    if security_config.allowed_domains:
        webview_config.allowed_hosts = list(security_config.allowed_domains)
    
    if security_config.blocked_domains:
        webview_config.blocked_hosts = list(security_config.blocked_domains)
    
    return webview_config