"""
PyElectron WebView Event System

This module provides comprehensive event handling for WebView instances,
including lifecycle events, user interactions, and security events.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .base import BaseWebView, WebViewEvent, WebViewEventType
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class EventPriority(Enum):
    """Event handler priority levels."""
    CRITICAL = 0    # Security, system-critical events
    HIGH = 1        # Application-critical events
    NORMAL = 2      # Regular application events
    LOW = 3         # Nice-to-have events
    DEBUG = 4       # Development/debugging events


@dataclass
class EventFilter:
    """Filter for event handling."""
    
    event_types: Optional[List[WebViewEventType]] = None
    webview_ids: Optional[List[str]] = None
    data_filters: Optional[Dict[str, Any]] = None
    
    def matches(self, event: WebViewEvent) -> bool:
        """Check if event matches filter criteria."""
        # Check event type
        if self.event_types and event.event_type not in self.event_types:
            return False
        
        # Check webview ID
        if self.webview_ids and event.webview_id not in self.webview_ids:
            return False
        
        # Check data filters
        if self.data_filters:
            for key, expected_value in self.data_filters.items():
                if key not in event.data or event.data[key] != expected_value:
                    return False
        
        return True


@dataclass
class EventHandler:
    """Event handler registration."""
    
    callback: Callable
    priority: EventPriority = EventPriority.NORMAL
    filter: Optional[EventFilter] = None
    once: bool = False
    enabled: bool = True
    handler_id: str = field(default_factory=lambda: str(__import__('uuid').uuid4()))
    
    async def handle_event(self, event: WebViewEvent) -> bool:
        """Handle event and return whether handler should be removed."""
        if not self.enabled:
            return False
        
        # Check filter
        if self.filter and not self.filter.matches(event):
            return False
        
        try:
            # Call handler
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback(event)
            else:
                self.callback(event)
            
            # Remove if it's a one-time handler
            return self.once
            
        except Exception as e:
            logger.error(f"Error in event handler {self.handler_id}: {e}")
            return False


class EventBus:
    """
    Central event bus for WebView events.
    
    Manages event registration, filtering, and dispatch with priority
    handling and performance monitoring.
    """
    
    def __init__(self):
        self.handlers: Dict[WebViewEventType, List[EventHandler]] = {}
        self.global_handlers: List[EventHandler] = []
        self.event_stats: Dict[str, int] = {}
        self.performance_stats: Dict[str, List[float]] = {}
        
        # Initialize handlers for each event type
        for event_type in WebViewEventType:
            self.handlers[event_type] = []
            self.event_stats[event_type.value] = 0
            self.performance_stats[event_type.value] = []
        
        logger.debug("EventBus initialized")
    
    def register_handler(self, event_type: WebViewEventType, callback: Callable,
                        priority: EventPriority = EventPriority.NORMAL,
                        filter: Optional[EventFilter] = None,
                        once: bool = False) -> str:
        """
        Register event handler.
        
        Args:
            event_type: Type of event to handle
            callback: Handler function
            priority: Handler priority
            filter: Optional event filter
            once: Whether handler should be removed after first call
            
        Returns:
            str: Handler ID for removal
        """
        handler = EventHandler(
            callback=callback,
            priority=priority,
            filter=filter,
            once=once
        )
        
        # Add to appropriate handler list
        self.handlers[event_type].append(handler)
        
        # Sort by priority (critical first)
        self.handlers[event_type].sort(key=lambda h: h.priority.value)
        
        logger.debug(f"Registered handler for {event_type.value} with priority {priority.value}")
        return handler.handler_id
    
    def register_global_handler(self, callback: Callable,
                               priority: EventPriority = EventPriority.NORMAL,
                               filter: Optional[EventFilter] = None,
                               once: bool = False) -> str:
        """
        Register global event handler for all event types.
        
        Args:
            callback: Handler function
            priority: Handler priority
            filter: Optional event filter
            once: Whether handler should be removed after first call
            
        Returns:
            str: Handler ID for removal
        """
        handler = EventHandler(
            callback=callback,
            priority=priority,
            filter=filter,
            once=once
        )
        
        self.global_handlers.append(handler)
        self.global_handlers.sort(key=lambda h: h.priority.value)
        
        logger.debug(f"Registered global handler with priority {priority.value}")
        return handler.handler_id
    
    def unregister_handler(self, handler_id: str) -> bool:
        """
        Unregister event handler.
        
        Args:
            handler_id: ID of handler to remove
            
        Returns:
            bool: True if handler was found and removed
        """
        # Check event-specific handlers
        for event_type, handlers in self.handlers.items():
            for i, handler in enumerate(handlers):
                if handler.handler_id == handler_id:
                    del handlers[i]
                    logger.debug(f"Unregistered handler {handler_id} for {event_type.value}")
                    return True
        
        # Check global handlers
        for i, handler in enumerate(self.global_handlers):
            if handler.handler_id == handler_id:
                del self.global_handlers[i]
                logger.debug(f"Unregistered global handler {handler_id}")
                return True
        
        logger.warning(f"Handler not found: {handler_id}")
        return False
    
    def enable_handler(self, handler_id: str) -> bool:
        """Enable event handler."""
        return self._set_handler_state(handler_id, True)
    
    def disable_handler(self, handler_id: str) -> bool:
        """Disable event handler."""
        return self._set_handler_state(handler_id, False)
    
    def _set_handler_state(self, handler_id: str, enabled: bool) -> bool:
        """Set handler enabled state."""
        # Check all handlers
        all_handlers = []
        for handlers in self.handlers.values():
            all_handlers.extend(handlers)
        all_handlers.extend(self.global_handlers)
        
        for handler in all_handlers:
            if handler.handler_id == handler_id:
                handler.enabled = enabled
                state = "enabled" if enabled else "disabled"
                logger.debug(f"Handler {handler_id} {state}")
                return True
        
        return False
    
    async def emit_event(self, event: WebViewEvent):
        """
        Emit event to all relevant handlers.
        
        Args:
            event: Event to emit
        """
        start_time = time.time()
        
        try:
            # Update statistics
            self.event_stats[event.event_type.value] += 1
            
            # Get handlers for this event type
            specific_handlers = self.handlers.get(event.event_type, [])
            
            # Combine with global handlers and sort by priority
            all_handlers = specific_handlers + self.global_handlers
            all_handlers.sort(key=lambda h: h.priority.value)
            
            # Process handlers
            handlers_to_remove = []
            
            for handler in all_handlers:
                try:
                    should_remove = await handler.handle_event(event)
                    if should_remove:
                        handlers_to_remove.append(handler.handler_id)
                        
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")
            
            # Remove one-time handlers
            for handler_id in handlers_to_remove:
                self.unregister_handler(handler_id)
            
            # Record performance
            duration = time.time() - start_time
            self.performance_stats[event.event_type.value].append(duration)
            
            # Keep only last 100 measurements
            if len(self.performance_stats[event.event_type.value]) > 100:
                self.performance_stats[event.event_type.value].pop(0)
            
            logger.debug(f"Event {event.event_type.value} processed in {duration:.3f}s")
            
        except Exception as e:
            logger.error(f"Error emitting event {event.event_type.value}: {e}")
    
    def get_handler_count(self, event_type: Optional[WebViewEventType] = None) -> int:
        """Get number of registered handlers."""
        if event_type:
            return len(self.handlers.get(event_type, []))
        else:
            total = len(self.global_handlers)
            for handlers in self.handlers.values():
                total += len(handlers)
            return total
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get event statistics."""
        stats = {
            'event_counts': self.event_stats.copy(),
            'handler_counts': {
                event_type.value: len(handlers)
                for event_type, handlers in self.handlers.items()
            },
            'global_handlers': len(self.global_handlers),
            'performance': {}
        }
        
        # Calculate performance stats
        for event_type, durations in self.performance_stats.items():
            if durations:
                stats['performance'][event_type] = {
                    'avg_duration': sum(durations) / len(durations),
                    'max_duration': max(durations),
                    'min_duration': min(durations),
                    'sample_count': len(durations)
                }
        
        return stats
    
    def clear_statistics(self):
        """Clear event statistics."""
        for event_type in WebViewEventType:
            self.event_stats[event_type.value] = 0
            self.performance_stats[event_type.value] = []
        
        logger.debug("Event statistics cleared")


class WebViewEventManager:
    """
    High-level event manager for WebView instances.
    
    Provides convenient methods for setting up common event patterns
    and integrating with the application lifecycle.
    """
    
    def __init__(self, webview: BaseWebView, event_bus: Optional[EventBus] = None):
        self.webview = webview
        self.event_bus = event_bus or EventBus()
        self.handler_ids: List[str] = []
        
        # Set up WebView event forwarding
        self._setup_webview_forwarding()
        
        logger.debug(f"EventManager initialized for WebView {webview.webview_id}")
    
    def _setup_webview_forwarding(self):
        """Set up event forwarding from WebView to event bus."""
        for event_type in WebViewEventType:
            self.webview.add_event_handler(event_type, self._forward_event)
    
    async def _forward_event(self, event: WebViewEvent):
        """Forward WebView event to event bus."""
        await self.event_bus.emit_event(event)
    
    def on_ready(self, callback: Callable, once: bool = False) -> str:
        """Register handler for WebView ready event."""
        return self.event_bus.register_handler(
            WebViewEventType.READY, callback, 
            priority=EventPriority.HIGH, once=once
        )
    
    def on_navigation(self, callback: Callable, url_pattern: str = None) -> str:
        """Register handler for navigation events."""
        filter = None
        if url_pattern:
            filter = EventFilter(data_filters={'url_pattern': url_pattern})
        
        return self.event_bus.register_handler(
            WebViewEventType.NAVIGATION_COMPLETE, callback,
            filter=filter
        )
    
    def on_error(self, callback: Callable, priority: EventPriority = EventPriority.HIGH) -> str:
        """Register handler for error events."""
        return self.event_bus.register_handler(
            WebViewEventType.NAVIGATION_ERROR, callback,
            priority=priority
        )
    
    def on_close(self, callback: Callable, priority: EventPriority = EventPriority.HIGH) -> str:
        """Register handler for close events."""
        return self.event_bus.register_handler(
            WebViewEventType.CLOSE_REQUESTED, callback,
            priority=priority
        )
    
    def on_console_message(self, callback: Callable, 
                          message_filter: str = None) -> str:
        """Register handler for console messages."""
        filter = None
        if message_filter:
            filter = EventFilter(data_filters={'message_contains': message_filter})
        
        return self.event_bus.register_handler(
            WebViewEventType.CONSOLE_MESSAGE, callback,
            filter=filter, priority=EventPriority.DEBUG
        )
    
    def setup_security_monitoring(self, violation_callback: Callable) -> List[str]:
        """Set up security event monitoring."""
        handler_ids = []
        
        # Monitor navigation for suspicious activity
        def check_navigation(event: WebViewEvent):
            url = event.data.get('url', '')
            if any(pattern in url.lower() for pattern in ['javascript:', 'data:', 'vbscript:']):
                violation_callback({
                    'type': 'suspicious_navigation',
                    'url': url,
                    'webview_id': event.webview_id
                })
        
        handler_ids.append(self.event_bus.register_handler(
            WebViewEventType.NAVIGATION_START, check_navigation,
            priority=EventPriority.CRITICAL
        ))
        
        # Monitor console for security violations
        def check_console(event: WebViewEvent):
            message = event.data.get('message', '')
            if 'security violation' in message.lower():
                violation_callback({
                    'type': 'console_security_violation',
                    'message': message,
                    'webview_id': event.webview_id
                })
        
        handler_ids.append(self.event_bus.register_handler(
            WebViewEventType.CONSOLE_MESSAGE, check_console,
            priority=EventPriority.CRITICAL
        ))
        
        return handler_ids
    
    def setup_performance_monitoring(self, threshold_ms: float = 1000) -> str:
        """Set up performance monitoring for slow operations."""
        def check_performance(event: WebViewEvent):
            duration = event.data.get('duration', 0)
            if duration > threshold_ms:
                logger.warning(
                    f"Slow operation detected: {event.event_type.value} "
                    f"took {duration:.2f}ms in WebView {event.webview_id}"
                )
        
        return self.event_bus.register_global_handler(
            check_performance, priority=EventPriority.DEBUG
        )
    
    def setup_lifecycle_logging(self) -> List[str]:
        """Set up comprehensive lifecycle event logging."""
        handler_ids = []
        
        lifecycle_events = [
            WebViewEventType.READY,
            WebViewEventType.NAVIGATION_START,
            WebViewEventType.NAVIGATION_COMPLETE,
            WebViewEventType.NAVIGATION_ERROR,
            WebViewEventType.CLOSE_REQUESTED,
        ]
        
        def log_lifecycle_event(event: WebViewEvent):
            logger.info(
                f"WebView {event.webview_id} lifecycle: {event.event_type.value} "
                f"at {time.strftime('%H:%M:%S', time.localtime(event.timestamp))}"
            )
        
        for event_type in lifecycle_events:
            handler_ids.append(self.event_bus.register_handler(
                event_type, log_lifecycle_event,
                priority=EventPriority.DEBUG
            ))
        
        return handler_ids
    
    def cleanup(self):
        """Clean up event manager."""
        # Remove all registered handlers
        for handler_id in self.handler_ids:
            self.event_bus.unregister_handler(handler_id)
        
        self.handler_ids.clear()
        logger.debug(f"EventManager cleaned up for WebView {self.webview.webview_id}")


# Global event bus instance
_global_event_bus = EventBus()


def get_global_event_bus() -> EventBus:
    """Get the global event bus instance."""
    return _global_event_bus


def create_event_manager(webview: BaseWebView, 
                        use_global_bus: bool = True) -> WebViewEventManager:
    """Create event manager for WebView."""
    event_bus = _global_event_bus if use_global_bus else EventBus()
    return WebViewEventManager(webview, event_bus)