"""
Unit tests for PyElectron WebView system

Tests the complete WebView stack including base classes, platform backends,
security, IPC integration, and event handling.
"""

import asyncio
import json
import platform
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyelectron.webview.base import (
    BaseWebView, WebViewConfig, WebViewFactory, WebViewInfo,
    WebViewEvent, WebViewEventType, WebViewState, SecurityPolicy,
    create_default_config
)
from pyelectron.webview.manager import WebViewManager, WebViewService, create_webview_manager
from pyelectron.webview.security import (
    WebViewSecurityConfig, SecurityPolicyManager, URLValidator,
    ContentSecurityPolicy
)
from pyelectron.webview.policies import (
    WebViewSecurityPolicy, ResourceType, ActionType, ResourceRule,
    PolicyTemplate, create_security_policy
)
from pyelectron.webview.events import (
    EventBus, EventHandler, EventFilter, EventPriority,
    WebViewEventManager, create_event_manager
)
from pyelectron.webview.ipc_bridge import WebViewIPCBridge, WebViewAPI, SystemAPI
from pyelectron.utils.errors import WebViewError, SecurityError


class MockWebView(BaseWebView):
    """Mock WebView implementation for testing."""
    
    def __init__(self, webview_id: str, config: WebViewConfig):
        super().__init__(webview_id, config)
        self.created = False
        self.current_url = None
        self.current_title = None
        self.executed_scripts = []
        
    async def create(self) -> None:
        self.created = True
        self.state = WebViewState.CREATED
        await self.emit_event(WebViewEventType.READY)
    
    async def load_url(self, url: str) -> None:
        if not self._validate_url(url):
            raise WebViewError(f"URL not allowed: {url}")
        
        self.current_url = url
        self.state = WebViewState.LOADING
        await self.emit_event(WebViewEventType.NAVIGATION_START, {'url': url})
        
        # Simulate loading
        await asyncio.sleep(0.01)
        
        self.state = WebViewState.LOADED
        await self.emit_event(WebViewEventType.NAVIGATION_COMPLETE, {'url': url})
    
    async def load_html(self, html: str, base_url=None) -> None:
        self.current_url = base_url or "about:blank"
        self.state = WebViewState.LOADING
        await self.emit_event(WebViewEventType.NAVIGATION_START, {'html': True})
        
        await asyncio.sleep(0.01)
        
        self.state = WebViewState.LOADED
        await self.emit_event(WebViewEventType.NAVIGATION_COMPLETE, {'html': True})
    
    async def execute_javascript(self, script: str):
        self.executed_scripts.append(script)
        
        # Simulate some common JavaScript results
        if 'document.title' in script:
            return self.current_title or "Test Page"
        elif 'window.location.href' in script:
            return self.current_url or "about:blank"
        elif 'alert' in script:
            await self.emit_event(WebViewEventType.ALERT, {'message': 'test alert'})
            return None
        else:
            return "script_result"
    
    async def show(self) -> None:
        pass
    
    async def hide(self) -> None:
        pass
    
    async def close(self) -> None:
        self.state = WebViewState.DESTROYED
        await self.emit_event(WebViewEventType.CLOSE_REQUESTED)
    
    async def resize(self, width: int, height: int) -> None:
        pass
    
    async def get_url(self) -> str:
        return self.current_url
    
    async def get_title(self) -> str:
        return self.current_title
    
    def set_security_policy(self, policy: SecurityPolicy) -> None:
        self.config.security_policy = policy


class TestWebViewConfig:
    """Test WebView configuration."""
    
    def test_default_config(self):
        """Test default WebView configuration."""
        config = WebViewConfig()
        
        assert config.width == 1024
        assert config.height == 768
        assert config.title == "PyElectron App"
        assert config.resizable is True
        assert config.security_policy == SecurityPolicy.BALANCED
        assert config.enable_dev_tools is False
        assert config.enable_pyelectron_api is True
    
    def test_custom_config(self):
        """Test custom WebView configuration."""
        config = WebViewConfig(
            width=800,
            height=600,
            title="Custom App",
            security_policy=SecurityPolicy.STRICT,
            enable_dev_tools=True,
            allowed_hosts=["example.com"],
        )
        
        assert config.width == 800
        assert config.height == 600
        assert config.title == "Custom App"
        assert config.security_policy == SecurityPolicy.STRICT
        assert config.enable_dev_tools is True
        assert config.allowed_hosts == ["example.com"]
    
    def test_create_default_config(self):
        """Test default config creation function."""
        config = create_default_config(
            title="Test App",
            width=1200,
            security_policy=SecurityPolicy.PERMISSIVE
        )
        
        assert config.title == "Test App"
        assert config.width == 1200
        assert config.security_policy == SecurityPolicy.PERMISSIVE
        assert config.enable_dev_tools is False  # Should remain default


class TestWebViewFactory:
    """Test WebView factory."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Register mock backend
        WebViewFactory.register_backend("TestOS", MockWebView)
    
    def test_register_backend(self):
        """Test backend registration."""
        backends = WebViewFactory.get_available_backends()
        assert "TestOS" in backends
    
    def test_create_webview(self):
        """Test WebView creation."""
        config = WebViewConfig(title="Test WebView")
        
        webview = WebViewFactory.create_webview("test-id", config, platform="TestOS")
        
        assert isinstance(webview, MockWebView)
        assert webview.webview_id == "test-id"
        assert webview.config.title == "Test WebView"
    
    def test_create_webview_unknown_platform(self):
        """Test WebView creation with unknown platform."""
        config = WebViewConfig()
        
        with pytest.raises(WebViewError) as exc_info:
            WebViewFactory.create_webview("test-id", config, platform="UnknownOS")
        
        assert "No WebView backend registered" in str(exc_info.value)


class TestMockWebView:
    """Test MockWebView implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = WebViewConfig(title="Test WebView")
        self.webview = MockWebView("test-webview", config)
    
    @pytest.mark.asyncio
    async def test_create_webview(self):
        """Test WebView creation."""
        assert not self.webview.created
        assert self.webview.state == WebViewState.CREATED
        
        await self.webview.create()
        
        assert self.webview.created
        assert self.webview.state == WebViewState.CREATED
    
    @pytest.mark.asyncio
    async def test_load_url(self):
        """Test URL loading."""
        await self.webview.create()
        
        await self.webview.load_url("https://example.com")
        
        assert self.webview.current_url == "https://example.com"
        assert self.webview.state == WebViewState.LOADED
    
    @pytest.mark.asyncio
    async def test_load_invalid_url(self):
        """Test loading invalid URL."""
        await self.webview.create()
        
        # Configure to block external URLs
        self.webview.config.allowed_hosts = ["localhost"]
        
        with pytest.raises(WebViewError):
            await self.webview.load_url("https://malicious.com")
    
    @pytest.mark.asyncio
    async def test_execute_javascript(self):
        """Test JavaScript execution."""
        await self.webview.create()
        
        result = await self.webview.execute_javascript("console.log('test')")
        
        assert "console.log('test')" in self.webview.executed_scripts
        assert result == "script_result"
    
    @pytest.mark.asyncio
    async def test_close_webview(self):
        """Test WebView closure."""
        await self.webview.create()
        
        await self.webview.close()
        
        assert self.webview.state == WebViewState.DESTROYED


@pytest.mark.asyncio
class TestWebViewManager:
    """Test WebView manager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        WebViewFactory.register_backend("TestOS", MockWebView)
        self.manager = create_webview_manager()
    
    def teardown_method(self):
        """Clean up after tests."""
        asyncio.run(self.manager.cleanup())
    
    async def test_create_webview(self):
        """Test WebView creation through manager."""
        config = WebViewConfig(title="Managed WebView")
        
        with patch('platform.system', return_value='TestOS'):
            webview_id = await self.manager.create_webview(config)
        
        assert webview_id in self.manager.webviews
        assert self.manager.get_webview_count() == 1
        
        info = self.manager.get_webview_info(webview_id)
        assert info.webview_id == webview_id
        assert info.backend == "MockWebView"
    
    async def test_close_webview(self):
        """Test WebView closure through manager."""
        config = WebViewConfig()
        
        with patch('platform.system', return_value='TestOS'):
            webview_id = await self.manager.create_webview(config)
        
        assert self.manager.get_webview_count() == 1
        
        await self.manager.close_webview(webview_id)
        
        assert self.manager.get_webview_count() == 0
        assert webview_id not in self.manager.webviews
    
    async def test_load_url_via_manager(self):
        """Test loading URL through manager."""
        config = WebViewConfig()
        
        with patch('platform.system', return_value='TestOS'):
            webview_id = await self.manager.create_webview(config)
        
        await self.manager.load_url(webview_id, "https://example.com")
        
        url = await self.manager.get_webview_url(webview_id)
        assert url == "https://example.com"
    
    async def test_execute_javascript_via_manager(self):
        """Test JavaScript execution through manager."""
        config = WebViewConfig()
        
        with patch('platform.system', return_value='TestOS'):
            webview_id = await self.manager.create_webview(config)
        
        result = await self.manager.execute_javascript(webview_id, "return 42")
        
        assert result == "script_result"
    
    async def test_list_webviews(self):
        """Test listing WebViews."""
        config = WebViewConfig()
        
        with patch('platform.system', return_value='TestOS'):
            webview_id1 = await self.manager.create_webview(config)
            webview_id2 = await self.manager.create_webview(config)
        
        webviews = self.manager.list_webviews()
        
        assert len(webviews) == 2
        assert webview_id1 in webviews
        assert webview_id2 in webviews
    
    async def test_close_all_webviews(self):
        """Test closing all WebViews."""
        config = WebViewConfig()
        
        with patch('platform.system', return_value='TestOS'):
            await self.manager.create_webview(config)
            await self.manager.create_webview(config)
        
        assert self.manager.get_webview_count() == 2
        
        await self.manager.close_all_webviews()
        
        assert self.manager.get_webview_count() == 0


class TestWebViewSecurity:
    """Test WebView security configuration."""
    
    def test_security_policy_manager(self):
        """Test security policy manager."""
        strict_config = SecurityPolicyManager.get_security_config(SecurityPolicy.STRICT)
        balanced_config = SecurityPolicyManager.get_security_config(SecurityPolicy.BALANCED)
        permissive_config = SecurityPolicyManager.get_security_config(SecurityPolicy.PERMISSIVE)
        
        # Strict should be most restrictive
        assert not strict_config.enable_javascript
        assert not strict_config.enable_plugins
        assert not strict_config.enable_third_party_cookies
        
        # Balanced should allow JavaScript but be cautious
        assert balanced_config.enable_javascript
        assert not balanced_config.enable_eval
        assert not balanced_config.enable_plugins
        
        # Permissive should allow most things
        assert permissive_config.enable_javascript
        assert permissive_config.enable_eval
        assert permissive_config.enable_plugins
    
    def test_url_validation(self):
        """Test URL validation."""
        config = SecurityPolicyManager.get_security_config(SecurityPolicy.BALANCED)
        
        # Valid URLs
        assert SecurityPolicyManager.validate_url("https://example.com", config)
        assert SecurityPolicyManager.validate_url("http://localhost:3000", config)
        
        # Invalid URLs based on config
        config.allowed_protocols = {"https"}
        assert not SecurityPolicyManager.validate_url("http://example.com", config)
        
        config.blocked_domains = {"malicious.com"}
        assert not SecurityPolicyManager.validate_url("https://malicious.com", config)
    
    def test_url_validator(self):
        """Test URL validator utility."""
        # Safe URLs
        assert URLValidator.is_safe_url("https://example.com")
        assert URLValidator.is_safe_url("http://localhost:3000")
        assert URLValidator.is_safe_url("file:///path/to/file.html")
        
        # Dangerous URLs
        assert not URLValidator.is_safe_url("javascript:alert('xss')")
        assert not URLValidator.is_safe_url("vbscript:msgbox('xss')")
        assert not URLValidator.is_safe_url("data:text/html,<script>alert('xss')</script>")
        
        # File URL validation
        assert URLValidator.is_safe_url("file:///path/to/file.html")
        assert URLValidator.is_safe_url("file:///path/to/image.png")
        assert not URLValidator.is_safe_url("file:///path/to/file.exe")
    
    def test_content_security_policy(self):
        """Test Content Security Policy generation."""
        csp = ContentSecurityPolicy(
            default_src=["'self'"],
            script_src=["'self'", "'unsafe-inline'"],
            style_src=["'self'", "'unsafe-inline'"],
        )
        
        header = csp.to_header_value()
        
        assert "default-src 'self'" in header
        assert "script-src 'self' 'unsafe-inline'" in header
        assert "style-src 'self' 'unsafe-inline'" in header
        assert "upgrade-insecure-requests" in header


class TestWebViewPolicies:
    """Test WebView security policies."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = WebViewConfig()
        self.webview = MockWebView("test-policy", config)
        self.security_config = SecurityPolicyManager.get_security_config(SecurityPolicy.BALANCED)
    
    def test_create_security_policy(self):
        """Test security policy creation."""
        policy = create_security_policy(self.webview, "balanced")
        
        assert isinstance(policy, WebViewSecurityPolicy)
        assert policy.webview == self.webview
    
    def test_resource_rule_matching(self):
        """Test resource rule matching."""
        from pyelectron.webview.policies import ResourceRule
        
        # Create rule to block scripts from external domains
        rule = ResourceRule(
            pattern=r'https://external\.com/.*',
            action=ActionType.BLOCK,
            resource_types={ResourceType.SCRIPT}
        )
        
        # Should match external script
        assert rule.matches("https://external.com/script.js", ResourceType.SCRIPT)
        
        # Should not match different domain
        assert not rule.matches("https://trusted.com/script.js", ResourceType.SCRIPT)
        
        # Should not match different resource type
        assert not rule.matches("https://external.com/image.png", ResourceType.IMAGE)
    
    def test_policy_templates(self):
        """Test policy templates."""
        # Development policy should be permissive
        dev_policy = PolicyTemplate.create_development_policy(self.webview)
        assert dev_policy.security_config.enable_dev_tools
        assert dev_policy.security_config.enable_mixed_content
        
        # Production policy should be stricter
        prod_policy = PolicyTemplate.create_production_policy(self.webview)
        assert not prod_policy.security_config.enable_dev_tools
        assert not prod_policy.security_config.enable_mixed_content
        
        # Kiosk policy should be most restrictive
        kiosk_policy = PolicyTemplate.create_kiosk_policy(self.webview)
        assert not kiosk_policy.security_config.enable_context_menu
        assert not kiosk_policy.security_config.enable_text_selection


class TestWebViewEvents:
    """Test WebView event system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.event_bus = EventBus()
        self.events_received = []
        
        def capture_event(event):
            self.events_received.append(event)
        
        self.capture_handler = capture_event
    
    def test_event_registration(self):
        """Test event handler registration."""
        handler_id = self.event_bus.register_handler(
            WebViewEventType.READY,
            self.capture_handler
        )
        
        assert isinstance(handler_id, str)
        assert self.event_bus.get_handler_count(WebViewEventType.READY) == 1
    
    def test_event_unregistration(self):
        """Test event handler unregistration."""
        handler_id = self.event_bus.register_handler(
            WebViewEventType.READY,
            self.capture_handler
        )
        
        success = self.event_bus.unregister_handler(handler_id)
        
        assert success
        assert self.event_bus.get_handler_count(WebViewEventType.READY) == 0
    
    @pytest.mark.asyncio
    async def test_event_emission(self):
        """Test event emission."""
        self.event_bus.register_handler(
            WebViewEventType.READY,
            self.capture_handler
        )
        
        event = WebViewEvent(
            event_type=WebViewEventType.READY,
            webview_id="test-webview",
            data={'test': 'data'},
            timestamp=time.time()
        )
        
        await self.event_bus.emit_event(event)
        
        assert len(self.events_received) == 1
        assert self.events_received[0].event_type == WebViewEventType.READY
        assert self.events_received[0].data['test'] == 'data'
    
    def test_event_filtering(self):
        """Test event filtering."""
        from pyelectron.webview.events import EventFilter
        
        # Create filter for specific webview
        filter = EventFilter(webview_ids=["target-webview"])
        
        # Create events
        target_event = WebViewEvent(
            event_type=WebViewEventType.READY,
            webview_id="target-webview"
        )
        
        other_event = WebViewEvent(
            event_type=WebViewEventType.READY,
            webview_id="other-webview"
        )
        
        assert filter.matches(target_event)
        assert not filter.matches(other_event)
    
    def test_event_priority(self):
        """Test event handler priority."""
        execution_order = []
        
        def high_priority_handler(event):
            execution_order.append("high")
        
        def low_priority_handler(event):
            execution_order.append("low")
        
        # Register handlers with different priorities
        self.event_bus.register_handler(
            WebViewEventType.READY,
            low_priority_handler,
            priority=EventPriority.LOW
        )
        
        self.event_bus.register_handler(
            WebViewEventType.READY,
            high_priority_handler,
            priority=EventPriority.HIGH
        )
        
        # Emit event
        event = WebViewEvent(
            event_type=WebViewEventType.READY,
            webview_id="test"
        )
        
        asyncio.run(self.event_bus.emit_event(event))
        
        # High priority should execute first
        assert execution_order == ["high", "low"]
    
    @pytest.mark.asyncio
    async def test_event_manager_integration(self):
        """Test WebView event manager integration."""
        config = WebViewConfig()
        webview = MockWebView("test-integration", config)
        
        event_manager = create_event_manager(webview, use_global_bus=False)
        
        ready_events = []
        event_manager.on_ready(lambda e: ready_events.append(e))
        
        # Trigger ready event
        await webview.create()
        
        # Give event system time to process
        await asyncio.sleep(0.01)
        
        assert len(ready_events) == 1
        assert ready_events[0].event_type == WebViewEventType.READY


class TestWebViewIPCBridge:
    """Test WebView IPC bridge."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = WebViewConfig(enable_pyelectron_api=True)
        self.webview = MockWebView("test-ipc", config)
        self.ipc_bridge = WebViewIPCBridge(self.webview)
    
    def test_webview_api(self):
        """Test built-in WebView API."""
        api = WebViewAPI(self.webview)
        
        # Test platform info
        assert hasattr(api, 'get_url')
        assert hasattr(api, 'get_title')
        assert hasattr(api, 'load_url')
        assert hasattr(api, 'resize')
    
    def test_system_api(self):
        """Test built-in System API."""
        api = SystemAPI()
        
        # Test ping
        assert api.ping() == "pong"
        
        # Test platform
        platform_name = api.get_platform()
        assert isinstance(platform_name, str)
    
    @pytest.mark.asyncio
    async def test_ipc_message_handling(self):
        """Test IPC message handling."""
        # Simulate IPC message from JavaScript
        message = {
            'type': 'pyelectron_ipc',
            'message_type': 'request',
            'id': 'test-123',
            'method': 'system.ping',
            'params': None
        }
        
        # This would normally be called by the WebView event system
        await self.ipc_bridge._handle_ipc_message(message)
        
        # Check that script was executed to send response
        assert len(self.webview.executed_scripts) > 0
    
    def test_service_registration(self):
        """Test custom service registration."""
        class CustomService:
            def custom_method(self):
                return "custom_result"
        
        service = CustomService()
        self.ipc_bridge.register_service("custom", service)
        
        # Verify service was registered
        methods = self.ipc_bridge.service_registry.list_methods()
        assert any("custom" in method for method in methods)


@pytest.mark.integration
class TestWebViewIntegration:
    """Integration tests for complete WebView system."""
    
    @pytest.mark.asyncio
    async def test_full_webview_lifecycle(self):
        """Test complete WebView lifecycle."""
        # Register mock backend
        WebViewFactory.register_backend("TestOS", MockWebView)
        
        # Create manager
        manager = create_webview_manager()
        
        try:
            # Create WebView
            config = WebViewConfig(title="Integration Test")
            
            with patch('platform.system', return_value='TestOS'):
                webview_id = await manager.create_webview(config)
            
            # Load content
            await manager.load_url(webview_id, "https://example.com")
            
            # Execute JavaScript
            result = await manager.execute_javascript(webview_id, "return 'test'")
            assert result == "script_result"
            
            # Get info
            info = manager.get_webview_info(webview_id)
            assert info.webview_id == webview_id
            assert info.state == WebViewState.LOADED
            
            # Close WebView
            await manager.close_webview(webview_id)
            
            assert manager.get_webview_count() == 0
            
        finally:
            await manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_security_policy_enforcement(self):
        """Test security policy enforcement."""
        WebViewFactory.register_backend("TestOS", MockWebView)
        
        config = WebViewConfig(
            security_policy=SecurityPolicy.STRICT,
            allowed_hosts=["trusted.com"]
        )
        
        with patch('platform.system', return_value='TestOS'):
            webview = WebViewFactory.create_webview("security-test", config)
        
        await webview.create()
        
        # Should allow trusted domain
        await webview.load_url("https://trusted.com/page.html")
        assert await webview.get_url() == "https://trusted.com/page.html"
        
        # Should block untrusted domain
        with pytest.raises(WebViewError):
            await webview.load_url("https://malicious.com/page.html")
    
    @pytest.mark.asyncio
    async def test_event_system_integration(self):
        """Test event system integration."""
        WebViewFactory.register_backend("TestOS", MockWebView)
        
        config = WebViewConfig()
        
        with patch('platform.system', return_value='TestOS'):
            webview = WebViewFactory.create_webview("event-test", config)
        
        # Set up event monitoring
        events_received = []
        
        def capture_event(event):
            events_received.append(event.event_type)
        
        event_manager = create_event_manager(webview, use_global_bus=False)
        event_manager.on_ready(capture_event)
        event_manager.on_navigation(capture_event)
        
        # Trigger events
        await webview.create()
        await webview.load_url("https://example.com")
        
        # Give events time to process
        await asyncio.sleep(0.01)
        
        assert WebViewEventType.READY in events_received
        assert WebViewEventType.NAVIGATION_COMPLETE in events_received