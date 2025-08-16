"""
PyElectron Application Class

This module provides the main PyElectronApp class that manages the complete
application lifecycle, coordinates processes, and provides the main API.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from pyelectron.core.process import ProcessManager, ProcessType
from pyelectron.core.window import WindowManager, WindowConfig
from pyelectron.state.manager import StateManager
from pyelectron.security.permissions import PermissionManager
from pyelectron.utils.config import ConfigManager
from pyelectron.utils.errors import PyElectronError, handle_exception
from pyelectron.utils.logging import get_logger
from pyelectron.utils.platform import PlatformUtils

logger = get_logger(__name__)


class PyElectronApp:
    """
    Main application class with simple lifecycle management.
    
    This is the primary entry point for PyElectron applications, providing
    a clean API for desktop app development with Python backends.
    """
    
    def __init__(
        self,
        name: str = "PyElectronApp",
        data_dir: Optional[Union[str, Path]] = None,
        config_file: Optional[Union[str, Path]] = None,
        development_mode: bool = False,
        log_level: str = "INFO",
        **config_options
    ):
        """
        Initialize PyElectron application.
        
        Args:
            name: Application name
            data_dir: Directory for application data storage
            config_file: Path to configuration file
            development_mode: Enable development features
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            **config_options: Additional configuration options
        """
        self.name = name
        self.development_mode = development_mode
        self.is_running = False
        self.is_initialized = False
        
        # Set up data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.home() / '.pyelectron' / name.lower().replace(' ', '_')
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize core components
        self.config_manager = ConfigManager(
            app_name=name,
            config_file=config_file,
            **config_options
        )
        
        self.process_manager = ProcessManager()
        self.state_manager = StateManager(app_name=name)
        self.permission_manager = PermissionManager()
        self.window_manager: Optional[WindowManager] = None
        
        # Platform utilities
        self.platform = PlatformUtils()
        
        # Event loop and lifecycle
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready_callbacks: list[Callable] = []
        self._exit_callbacks: list[Callable] = []
        
        # API registry for exposing Python functions to frontend
        self.api_registry: Dict[str, Callable] = {}
        
        logger.info(f"PyElectronApp '{name}' initialized")
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get application configuration."""
        return self.config_manager.get_all()
    
    @handle_exception
    async def _initialize_basic(self):
        """Initialize basic app components without WebView."""
        if self.is_initialized:
            logger.warning("App already initialized")
            return
        
        logger.info("Initializing PyElectron application")
        
        # Validate platform
        platform_available, platform_message = self.platform.check_webview_availability()
        if not platform_available and not os.getenv("PYELECTRON_TEST_MODE"):
            raise PyElectronError(
                f"WebView not available on this platform: {platform_message}",
                details={'platform': sys.platform}
            )
        
        # Initialize state management
        await self.state_manager.initialize()
        
        # Set up process monitoring
        await self.process_manager.start_monitoring()
        
        # Register shutdown handlers
        self.process_manager.register_shutdown_handler(self._shutdown_handler)
        
        self.is_initialized = True
        logger.info("PyElectron application initialized successfully")
    
    @handle_exception
    async def initialize(self):
        """
        Initialize the application with full WebView support.
        
        This method sets up all components including WebView integration.
        Call this before running the application.
        """
        await self._initialize_basic()
        
        # Initialize window manager with WebView
        if not self.window_manager:
            self.window_manager = WindowManager()
            await self.window_manager.initialize()
        
        logger.info("Full application initialization completed")
    
    @handle_exception
    async def start(self):
        """
        Start application with proper initialization.
        
        This is the async entry point for running PyElectron applications.
        """
        if self.is_running:
            logger.warning("Application already running")
            return
        
        logger.info(f"Starting PyElectron application: {self.name}")
        
        try:
            # Initialize if not already done
            if not self.is_initialized:
                await self.initialize()
            
            # Set running state
            self.is_running = True
            
            # Execute ready callbacks
            for callback in self._ready_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error(f"Error in ready callback: {str(e)}")
            
            logger.info("PyElectron application started successfully")
            
        except Exception as e:
            self.is_running = False
            logger.error(f"Failed to start application: {str(e)}")
            raise
    
    @handle_exception
    async def stop(self):
        """
        Graceful shutdown with cleanup.
        
        This method properly shuts down all components and cleans up resources.
        """
        if not self.is_running:
            logger.warning("Application not running")
            return
        
        logger.info("Stopping PyElectron application")
        
        try:
            self.is_running = False
            
            # Execute exit callbacks
            for callback in self._exit_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error(f"Error in exit callback: {str(e)}")
            
            # Shutdown components in reverse order
            if self.window_manager:
                await self.window_manager.cleanup()
            
            await self.process_manager.shutdown()
            await self.state_manager.cleanup()
            
            logger.info("PyElectron application stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during application shutdown: {str(e)}")
            raise
    
    def run(self):
        """
        Main entry point for applications.
        
        This is the synchronous entry point that sets up the event loop
        and runs the application until completion.
        """
        logger.info(f"Running PyElectron application: {self.name}")
        
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_running_loop()
                logger.info("Using existing event loop")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.info("Created new event loop")
            
            self._loop = loop
            
            # Run the application
            loop.run_until_complete(self._run_async())
            
        except KeyboardInterrupt:
            logger.info("Application interrupted by user")
        except Exception as e:
            logger.error(f"Application error: {str(e)}", exc_info=True)
            raise
        finally:
            # Ensure cleanup
            if self._loop and not self._loop.is_closed():
                try:
                    self._loop.run_until_complete(self.cleanup())
                except Exception as e:
                    logger.error(f"Error during cleanup: {str(e)}")
                finally:
                    self._loop.close()
    
    async def _run_async(self):
        """Async application runner."""
        try:
            await self.start()
            
            # Keep running until stopped
            while self.is_running:
                await asyncio.sleep(0.1)
                
        finally:
            await self.stop()
    
    async def cleanup(self):
        """Clean up application resources."""
        logger.info("Cleaning up application resources")
        
        try:
            if self.is_running:
                await self.stop()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    def on_ready(self, callback: Callable):
        """
        Register callback to run when application is ready.
        
        Args:
            callback: Function to call when app is ready
        """
        self._ready_callbacks.append(callback)
        logger.debug(f"Registered ready callback: {callback.__name__}")
    
    def on_exit(self, callback: Callable):
        """
        Register callback to run when application exits.
        
        Args:
            callback: Function to call when app exits
        """
        self._exit_callbacks.append(callback)
        logger.debug(f"Registered exit callback: {callback.__name__}")
    
    async def _shutdown_handler(self):
        """Internal shutdown handler for process manager."""
        logger.info("Shutdown handler called")
        if self.is_running:
            await self.stop()
    
    # API Management for Frontend Communication
    
    def expose_api(self, name: str):
        """
        Decorator to expose Python function to frontend.
        
        Args:
            name: Name to expose the function as
            
        Example:
            @app.expose_api('process_data')
            async def process_data(data):
                return processed_data
        """
        def decorator(func: Callable):
            self.api_registry[name] = func
            logger.debug(f"Exposed API function: {name}")
            return func
        return decorator
    
    def register_api_function(self, name: str, func: Callable):
        """
        Register a function for API exposure.
        
        Args:
            name: API name
            func: Function to expose
        """
        self.api_registry[name] = func
        logger.debug(f"Registered API function: {name}")
    
    def get_api_function(self, name: str) -> Optional[Callable]:
        """Get registered API function by name."""
        return self.api_registry.get(name)
    
    def list_api_functions(self) -> Dict[str, Callable]:
        """Get all registered API functions."""
        return self.api_registry.copy()
    
    # Window Management
    
    async def create_window(
        self, 
        config: Optional[WindowConfig] = None,
        **kwargs
    ) -> str:
        """
        Create a new application window.
        
        Args:
            config: Window configuration
            **kwargs: Configuration options
            
        Returns:
            str: Window ID
        """
        if not self.window_manager:
            raise PyElectronError("Window manager not initialized")
        
        if not config:
            config = WindowConfig(**kwargs)
        
        return await self.window_manager.create_window(config)
    
    async def close_window(self, window_id: str):
        """Close a specific window."""
        if not self.window_manager:
            raise PyElectronError("Window manager not initialized")
        
        await self.window_manager.close_window(window_id)
    
    # Process Management
    
    def spawn_worker(
        self, 
        name: str, 
        target: Callable, 
        *args, 
        **kwargs
    ):
        """
        Spawn a worker process.
        
        Args:
            name: Process name
            target: Function to run
            *args: Arguments for target function
            **kwargs: Keyword arguments for target function
        """
        return self.process_manager.spawn_worker(name, target, args, **kwargs)
    
    def terminate_worker(self, name: str):
        """Terminate a worker process."""
        return self.process_manager.terminate_process(name)
    
    # State Management
    
    async def get_state(self, key: str, default: Any = None) -> Any:
        """Get application state value."""
        return await self.state_manager.get(key, default)
    
    async def set_state(self, key: str, value: Any):
        """Set application state value."""
        await self.state_manager.set(key, value)
    
    # Configuration
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config_manager.get(key, default)
    
    def set_config(self, key: str, value: Any):
        """Set configuration value."""
        self.config_manager.set(key, value)
    
    # Utility Methods
    
    def get_app_info(self) -> Dict[str, Any]:
        """Get comprehensive application information."""
        return {
            'name': self.name,
            'data_dir': str(self.data_dir),
            'development_mode': self.development_mode,
            'is_running': self.is_running,
            'is_initialized': self.is_initialized,
            'platform_info': self.platform.get_platform_info(),
            'process_info': self.process_manager.get_system_info(),
            'config': self.config,
            'api_functions': list(self.api_registry.keys()),
        }
    
    def __repr__(self) -> str:
        """String representation of the application."""
        status = "running" if self.is_running else "stopped"
        return f"PyElectronApp(name='{self.name}', status='{status}')"