"""
PyElectron WebView Security Policies

This module implements comprehensive security policies for WebView instances,
including permission management, content filtering, and runtime protection.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Callable, Any
from urllib.parse import urlparse

from .base import BaseWebView, SecurityPolicy
from .security import WebViewSecurityConfig, URLValidator
from pyelectron.security import Permission, PermissionManager
from pyelectron.utils.errors import SecurityError, PermissionError
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class ResourceType(Enum):
    """Types of web resources that can be filtered."""
    DOCUMENT = "document"
    STYLESHEET = "stylesheet"
    IMAGE = "image"
    MEDIA = "media"
    FONT = "font"
    SCRIPT = "script"
    XHR = "xmlhttprequest"
    FETCH = "fetch"
    WEBSOCKET = "websocket"
    OTHER = "other"


class ActionType(Enum):
    """Actions that can be taken on resources."""
    ALLOW = "allow"
    BLOCK = "block"
    REDIRECT = "redirect"
    MODIFY = "modify"


@dataclass
class ResourceRule:
    """Rule for filtering web resources."""
    
    pattern: str
    action: ActionType
    resource_types: Set[ResourceType] = field(default_factory=set)
    redirect_url: Optional[str] = None
    priority: int = 0
    description: Optional[str] = None
    
    def matches(self, url: str, resource_type: ResourceType) -> bool:
        """Check if rule matches URL and resource type."""
        # Check resource type filter
        if self.resource_types and resource_type not in self.resource_types:
            return False
        
        # Check URL pattern
        try:
            return bool(re.search(self.pattern, url, re.IGNORECASE))
        except re.error:
            logger.error(f"Invalid regex pattern in rule: {self.pattern}")
            return False


@dataclass
class PermissionRule:
    """Rule for managing WebView permissions."""
    
    domain_pattern: str
    permissions: Set[Permission]
    action: ActionType
    expiry: Optional[float] = None
    description: Optional[str] = None
    
    def matches_domain(self, domain: str) -> bool:
        """Check if rule matches domain."""
        try:
            return bool(re.search(self.domain_pattern, domain, re.IGNORECASE))
        except re.error:
            logger.error(f"Invalid regex pattern in permission rule: {self.domain_pattern}")
            return False


class WebViewSecurityPolicy:
    """
    Comprehensive security policy for WebView instances.
    
    Manages resource filtering, permission control, content validation,
    and runtime security enforcement.
    """
    
    def __init__(self, webview: BaseWebView, security_config: WebViewSecurityConfig):
        self.webview = webview
        self.security_config = security_config
        self.permission_manager = PermissionManager()
        
        # Policy rules
        self.resource_rules: List[ResourceRule] = []
        self.permission_rules: List[PermissionRule] = []
        
        # Runtime state
        self.blocked_resources: Set[str] = set()
        self.allowed_domains: Set[str] = set()
        self.blocked_domains: Set[str] = set()
        
        # Event handlers
        self.violation_handlers: List[Callable] = []
        
        # Initialize default policies
        self._initialize_default_policies()
        
        logger.debug(f"Security policy initialized for WebView {webview.webview_id}")
    
    def _initialize_default_policies(self):
        """Initialize default security policies based on security level."""
        policy_level = self.webview.config.security_policy
        
        if policy_level == SecurityPolicy.STRICT:
            self._add_strict_policies()
        elif policy_level == SecurityPolicy.BALANCED:
            self._add_balanced_policies()
        else:  # PERMISSIVE
            self._add_permissive_policies()
    
    def _add_strict_policies(self):
        """Add strict security policies."""
        # Block all external resources except HTTPS
        self.add_resource_rule(ResourceRule(
            pattern=r'^(?!https:).*',
            action=ActionType.BLOCK,
            description="Block non-HTTPS resources"
        ))
        
        # Block all scripts except from same origin
        self.add_resource_rule(ResourceRule(
            pattern=r'.*',
            action=ActionType.BLOCK,
            resource_types={ResourceType.SCRIPT},
            description="Block external scripts"
        ))
        
        # Block dangerous file types
        dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.com', '.pif']
        for ext in dangerous_extensions:
            self.add_resource_rule(ResourceRule(
                pattern=f'.*\\{ext}$',
                action=ActionType.BLOCK,
                description=f"Block {ext} files"
            ))
        
        # Deny all permissions by default
        self.permission_manager.deny(
            Permission.CAMERA, Permission.MICROPHONE, Permission.LOCATION,
            Permission.NOTIFICATIONS, Permission.CLIPBOARD
        )
    
    def _add_balanced_policies(self):
        """Add balanced security policies."""
        # Allow HTTPS and same-origin HTTP
        self.add_resource_rule(ResourceRule(
            pattern=r'^https:.*',
            action=ActionType.ALLOW,
            priority=100,
            description="Allow HTTPS resources"
        ))
        
        # Block dangerous protocols
        dangerous_protocols = ['javascript:', 'vbscript:', 'file:', 'ftp:']
        for protocol in dangerous_protocols:
            self.add_resource_rule(ResourceRule(
                pattern=f'^{re.escape(protocol)}',
                action=ActionType.BLOCK,
                priority=200,
                description=f"Block {protocol} protocol"
            ))
        
        # Block tracking and ads (basic list)
        tracking_domains = [
            'doubleclick.net', 'googleadservices.com', 'googlesyndication.com',
            'facebook.com/tr', 'google-analytics.com'
        ]
        for domain in tracking_domains:
            self.add_resource_rule(ResourceRule(
                pattern=f'.*{re.escape(domain)}.*',
                action=ActionType.BLOCK,
                description=f"Block tracking domain: {domain}"
            ))
        
        # Require user permission for sensitive APIs
        self.add_permission_rule(PermissionRule(
            domain_pattern='.*',
            permissions={Permission.CAMERA, Permission.MICROPHONE, Permission.LOCATION},
            action=ActionType.BLOCK,
            description="Require explicit permission for sensitive APIs"
        ))
    
    def _add_permissive_policies(self):
        """Add permissive security policies."""
        # Allow most resources
        self.add_resource_rule(ResourceRule(
            pattern=r'.*',
            action=ActionType.ALLOW,
            description="Allow all resources (permissive mode)"
        ))
        
        # Only block obvious malware patterns
        malware_patterns = [
            r'.*\.exe(\?.*)?$',
            r'.*malware.*',
            r'.*virus.*',
            r'javascript:.*eval.*'
        ]
        
        for pattern in malware_patterns:
            self.add_resource_rule(ResourceRule(
                pattern=pattern,
                action=ActionType.BLOCK,
                priority=100,
                description=f"Block malware pattern: {pattern}"
            ))
    
    def add_resource_rule(self, rule: ResourceRule):
        """Add resource filtering rule."""
        self.resource_rules.append(rule)
        # Sort by priority (higher priority first)
        self.resource_rules.sort(key=lambda r: r.priority, reverse=True)
        
        logger.debug(f"Added resource rule: {rule.description or rule.pattern}")
    
    def add_permission_rule(self, rule: PermissionRule):
        """Add permission rule."""
        self.permission_rules.append(rule)
        logger.debug(f"Added permission rule: {rule.description or rule.domain_pattern}")
    
    def check_resource_access(self, url: str, resource_type: ResourceType) -> ActionType:
        """Check if resource access should be allowed."""
        try:
            # Validate URL first
            if not URLValidator.is_safe_url(url):
                self._log_violation("unsafe_url", url)
                return ActionType.BLOCK
            
            # Apply resource rules in priority order
            for rule in self.resource_rules:
                if rule.matches(url, resource_type):
                    if rule.action == ActionType.BLOCK:
                        self._log_violation("resource_blocked", url, rule.description)
                        self.blocked_resources.add(url)
                    
                    return rule.action
            
            # Default allow if no rules match
            return ActionType.ALLOW
            
        except Exception as e:
            logger.error(f"Error checking resource access for {url}: {e}")
            return ActionType.BLOCK
    
    def check_permission(self, domain: str, permission: Permission) -> bool:
        """Check if permission should be granted for domain."""
        try:
            # Apply permission rules
            for rule in self.permission_rules:
                if rule.matches_domain(domain):
                    if rule.action == ActionType.ALLOW:
                        return True
                    elif rule.action == ActionType.BLOCK:
                        self._log_violation("permission_blocked", domain, f"Permission: {permission.value}")
                        return False
            
            # Check with permission manager
            return self.permission_manager.check(permission)
            
        except Exception as e:
            logger.error(f"Error checking permission {permission.value} for {domain}: {e}")
            return False
    
    def validate_navigation(self, url: str) -> bool:
        """Validate navigation attempt."""
        try:
            # Basic URL validation
            if not URLValidator.is_safe_url(url):
                self._log_violation("unsafe_navigation", url)
                return False
            
            # Check against WebView configuration
            if not self.webview._validate_url(url):
                self._log_violation("policy_violation", url)
                return False
            
            # Check resource rules for document type
            action = self.check_resource_access(url, ResourceType.DOCUMENT)
            
            return action == ActionType.ALLOW
            
        except Exception as e:
            logger.error(f"Error validating navigation to {url}: {e}")
            return False
    
    def validate_javascript_execution(self, script: str) -> bool:
        """Validate JavaScript execution attempt."""
        if not self.security_config.enable_javascript:
            self._log_violation("javascript_disabled", script[:100])
            return False
        
        # Check for dangerous patterns
        dangerous_patterns = [
            r'eval\s*\(',
            r'Function\s*\(',
            r'setTimeout\s*\(\s*["\']',
            r'setInterval\s*\(\s*["\']',
            r'document\.write\s*\(',
            r'innerHTML\s*=',
            r'outerHTML\s*=',
        ]
        
        if not self.security_config.enable_eval:
            for pattern in dangerous_patterns:
                if re.search(pattern, script, re.IGNORECASE):
                    self._log_violation("dangerous_javascript", script[:100], pattern)
                    return False
        
        return True
    
    def filter_content(self, content: str, content_type: str) -> str:
        """Filter potentially dangerous content."""
        if content_type.startswith('text/html'):
            return self._filter_html_content(content)
        elif content_type.startswith('text/css'):
            return self._filter_css_content(content)
        elif content_type.startswith('application/javascript'):
            return self._filter_javascript_content(content)
        
        return content
    
    def _filter_html_content(self, html: str) -> str:
        """Filter HTML content for security."""
        # Remove dangerous tags and attributes
        dangerous_tags = ['script', 'object', 'embed', 'iframe', 'frame']
        dangerous_attrs = ['onload', 'onerror', 'onclick', 'onmouseover']
        
        filtered = html
        
        # Remove dangerous tags
        for tag in dangerous_tags:
            pattern = f'<{tag}[^>]*>.*?</{tag}>'
            filtered = re.sub(pattern, '', filtered, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove dangerous attributes
        for attr in dangerous_attrs:
            pattern = f'{attr}\\s*=\\s*["\'][^"\']*["\']'
            filtered = re.sub(pattern, '', filtered, flags=re.IGNORECASE)
        
        return filtered
    
    def _filter_css_content(self, css: str) -> str:
        """Filter CSS content for security."""
        # Remove javascript: URLs and expressions
        dangerous_patterns = [
            r'javascript\s*:',
            r'expression\s*\(',
            r'@import\s+url\s*\(',
        ]
        
        filtered = css
        for pattern in dangerous_patterns:
            filtered = re.sub(pattern, '', filtered, flags=re.IGNORECASE)
        
        return filtered
    
    def _filter_javascript_content(self, js: str) -> str:
        """Filter JavaScript content for security."""
        if not self.security_config.enable_javascript:
            return "// JavaScript execution disabled by security policy"
        
        # In a production implementation, this could use a JavaScript parser
        # to perform more sophisticated filtering
        
        return js
    
    def _log_violation(self, violation_type: str, resource: str, details: str = None):
        """Log security violation."""
        violation_data = {
            'type': violation_type,
            'resource': resource,
            'webview_id': self.webview.webview_id,
            'timestamp': __import__('time').time()
        }
        
        if details:
            violation_data['details'] = details
        
        logger.warning(f"Security violation [{violation_type}]: {resource}")
        
        # Notify violation handlers
        for handler in self.violation_handlers:
            try:
                handler(violation_data)
            except Exception as e:
                logger.error(f"Error in violation handler: {e}")
    
    def add_violation_handler(self, handler: Callable):
        """Add security violation handler."""
        self.violation_handlers.append(handler)
        logger.debug("Added security violation handler")
    
    def get_violation_stats(self) -> Dict[str, Any]:
        """Get security violation statistics."""
        return {
            'blocked_resources_count': len(self.blocked_resources),
            'blocked_resources': list(self.blocked_resources)[-10],  # Last 10
            'active_rules_count': len(self.resource_rules),
            'permission_rules_count': len(self.permission_rules),
        }
    
    def export_policy(self) -> Dict[str, Any]:
        """Export policy configuration."""
        return {
            'security_level': self.webview.config.security_policy.value,
            'resource_rules': [
                {
                    'pattern': rule.pattern,
                    'action': rule.action.value,
                    'resource_types': [rt.value for rt in rule.resource_types],
                    'priority': rule.priority,
                    'description': rule.description
                }
                for rule in self.resource_rules
            ],
            'permission_rules': [
                {
                    'domain_pattern': rule.domain_pattern,
                    'permissions': [p.value for p in rule.permissions],
                    'action': rule.action.value,
                    'description': rule.description
                }
                for rule in self.permission_rules
            ]
        }


class PolicyTemplate:
    """Predefined policy templates for common use cases."""
    
    @staticmethod
    def create_development_policy(webview: BaseWebView) -> WebViewSecurityPolicy:
        """Create policy suitable for development."""
        config = WebViewSecurityConfig(
            enable_dev_tools=True,
            enable_mixed_content=True,
            enable_javascript=True,
            enable_eval=True,
        )
        
        policy = WebViewSecurityPolicy(webview, config)
        
        # Allow localhost and common dev servers
        dev_domains = ['localhost', '127.0.0.1', '0.0.0.0', 'dev.local']
        for domain in dev_domains:
            policy.add_resource_rule(ResourceRule(
                pattern=f'.*{re.escape(domain)}.*',
                action=ActionType.ALLOW,
                priority=100,
                description=f"Allow dev domain: {domain}"
            ))
        
        return policy
    
    @staticmethod
    def create_production_policy(webview: BaseWebView) -> WebViewSecurityPolicy:
        """Create policy suitable for production."""
        config = WebViewSecurityConfig(
            enable_dev_tools=False,
            enable_mixed_content=False,
            enable_javascript=True,
            enable_eval=False,
        )
        
        policy = WebViewSecurityPolicy(webview, config)
        
        # Strict production rules
        policy.add_resource_rule(ResourceRule(
            pattern=r'^(?!https:).*',
            action=ActionType.BLOCK,
            priority=200,
            description="Require HTTPS in production"
        ))
        
        return policy
    
    @staticmethod
    def create_kiosk_policy(webview: BaseWebView) -> WebViewSecurityPolicy:
        """Create policy suitable for kiosk mode."""
        config = WebViewSecurityConfig(
            enable_dev_tools=False,
            enable_context_menu=False,
            enable_text_selection=False,
            enable_drag_drop=False,
            enable_javascript=True,
            enable_eval=False,
        )
        
        policy = WebViewSecurityPolicy(webview, config)
        
        # Very restrictive for kiosk
        policy.add_resource_rule(ResourceRule(
            pattern=r'.*',
            action=ActionType.BLOCK,
            description="Block all by default"
        ))
        
        return policy


def create_security_policy(webview: BaseWebView, 
                          template: str = "balanced") -> WebViewSecurityPolicy:
    """Create security policy using a template."""
    if template == "development":
        return PolicyTemplate.create_development_policy(webview)
    elif template == "production":
        return PolicyTemplate.create_production_policy(webview)
    elif template == "kiosk":
        return PolicyTemplate.create_kiosk_policy(webview)
    else:
        # Default balanced policy
        config = WebViewSecurityConfig()
        return WebViewSecurityPolicy(webview, config)