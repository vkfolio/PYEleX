"""
PyElectron Process Management

This module provides simplified but robust process management for PyElectron
applications, including multi-process architecture and lifecycle management.
"""

import asyncio
import multiprocessing as mp
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from pyelectron.utils.errors import ProcessError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class ProcessType(Enum):
    """Types of processes in PyElectron architecture."""
    
    MAIN = "main"
    RENDERER = "renderer"
    WORKER = "worker"


class ProcessStatus(Enum):
    """Process status enumeration."""
    
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ProcessConfig:
    """Configuration for spawning processes."""
    
    type: ProcessType
    name: str
    target: Optional[Callable] = None
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    daemon: bool = True
    restart_on_failure: bool = False
    max_restarts: int = 3
    restart_delay: float = 1.0
    timeout: float = 30.0
    env: Optional[Dict[str, str]] = None
    working_directory: Optional[Path] = None
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.type != ProcessType.MAIN and not self.target:
            raise ProcessError(
                f"Process target is required for {self.type.value} processes",
                details={'process_type': self.type.value, 'name': self.name}
            )


@dataclass
class ProcessInfo:
    """Information about a running process."""
    
    config: ProcessConfig
    process: mp.Process
    status: ProcessStatus
    pid: Optional[int] = None
    started_at: Optional[float] = None
    restart_count: int = 0
    last_restart: Optional[float] = None
    
    @property
    def is_alive(self) -> bool:
        """Check if process is alive."""
        return self.process and self.process.is_alive()
    
    @property
    def uptime(self) -> Optional[float]:
        """Get process uptime in seconds."""
        if self.started_at and self.status == ProcessStatus.RUNNING:
            return time.time() - self.started_at
        return None


class ProcessManager:
    """
    Simplified process management without complex orchestration.
    
    Manages the lifecycle of PyElectron processes including spawning,
    monitoring, and cleanup.
    """
    
    def __init__(self):
        self.processes: Dict[str, ProcessInfo] = {}
        self.shutdown_handlers: List[Callable] = []
        self.main_process = mp.current_process()
        self._monitor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("ProcessManager initialized")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        if sys.platform != 'win32':
            # Unix systems
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        else:
            # Windows
            signal.signal(signal.SIGBREAK, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        asyncio.create_task(self.shutdown())
    
    @handle_exception
    def spawn_worker(
        self, 
        name: str, 
        target: Callable, 
        args: Tuple[Any, ...] = (),
        **kwargs
    ) -> ProcessInfo:
        """
        Spawn a worker process - simple and reliable.
        
        Args:
            name: Unique process name
            target: Function to run in the process
            args: Arguments to pass to target function
            **kwargs: Additional configuration options
            
        Returns:
            ProcessInfo: Information about the spawned process
            
        Raises:
            ProcessError: If process spawning fails
        """
        if name in self.processes:
            logger.warning(f"Process {name} already exists, terminating first")
            self.terminate_process(name)
        
        # Create process configuration
        config = ProcessConfig(
            type=ProcessType.WORKER,
            name=name,
            target=target,
            args=args,
            **kwargs
        )
        
        return self._spawn_process(config)
    
    def spawn_renderer(
        self,
        name: str,
        target: Callable,
        args: Tuple[Any, ...] = (),
        **kwargs
    ) -> ProcessInfo:
        """
        Spawn a renderer process for WebView.
        
        Args:
            name: Unique process name
            target: Function to run in the process
            args: Arguments to pass to target function
            **kwargs: Additional configuration options
            
        Returns:
            ProcessInfo: Information about the spawned process
        """
        if name in self.processes:
            logger.warning(f"Renderer process {name} already exists, terminating first")
            self.terminate_process(name)
        
        config = ProcessConfig(
            type=ProcessType.RENDERER,
            name=name,
            target=target,
            args=args,
            daemon=False,  # Renderer processes should not be daemon
            **kwargs
        )
        
        return self._spawn_process(config)
    
    @handle_exception
    def _spawn_process(self, config: ProcessConfig) -> ProcessInfo:
        """Internal method to spawn a process."""
        logger.info(f"Spawning {config.type.value} process: {config.name}")
        
        try:
            # Set up environment
            env = os.environ.copy()
            if config.env:
                env.update(config.env)
            
            # Create process with proper context
            if sys.platform == 'win32':
                # Windows requires special handling
                mp_context = mp.get_context('spawn')
            else:
                # Unix systems can use fork
                mp_context = mp.get_context('fork')
            
            process = mp_context.Process(
                target=self._process_wrapper,
                args=(config.target, config.args, config.kwargs, config.name),
                name=f"pyelectron-{config.type.value}-{config.name}",
                daemon=config.daemon
            )
            
            # Create process info
            process_info = ProcessInfo(
                config=config,
                process=process,
                status=ProcessStatus.STARTING
            )
            
            # Start the process
            process.start()
            process_info.pid = process.pid
            process_info.started_at = time.time()
            process_info.status = ProcessStatus.RUNNING
            
            # Store process info
            self.processes[config.name] = process_info
            
            logger.info(
                f"Process {config.name} started successfully with PID {process.pid}"
            )
            
            return process_info
            
        except Exception as e:
            raise ProcessError(
                f"Failed to spawn process {config.name}: {str(e)}",
                details={
                    'process_name': config.name,
                    'process_type': config.type.value,
                    'error': str(e)
                }
            ) from e
    
    @staticmethod
    def _process_wrapper(
        target: Callable, 
        args: Tuple[Any, ...], 
        kwargs: Dict[str, Any],
        process_name: str
    ):
        """
        Wrapper function that runs in the spawned process.
        
        This provides common initialization and error handling
        for all PyElectron processes.
        """
        try:
            # Set process title for better monitoring
            if hasattr(os, 'setpgrp'):
                os.setpgrp()  # Create new process group
            
            # Set up logging for the process
            process_logger = get_logger(f"process.{process_name}")
            process_logger.info(f"Process {process_name} starting")
            
            # Run the target function
            result = target(*args, **kwargs)
            
            process_logger.info(f"Process {process_name} completed successfully")
            return result
            
        except KeyboardInterrupt:
            process_logger.info(f"Process {process_name} interrupted")
        except Exception as e:
            process_logger.error(f"Process {process_name} failed: {str(e)}", exc_info=True)
            raise
        finally:
            process_logger.info(f"Process {process_name} shutting down")
    
    @handle_exception
    def terminate_process(self, name: str, timeout: float = 5.0) -> bool:
        """
        Clean process termination with timeout.
        
        Args:
            name: Process name to terminate
            timeout: Maximum time to wait for graceful shutdown
            
        Returns:
            bool: True if process terminated successfully
        """
        if name not in self.processes:
            logger.warning(f"Process {name} not found")
            return False
        
        process_info = self.processes[name]
        process = process_info.process
        
        if not process.is_alive():
            logger.info(f"Process {name} already terminated")
            process_info.status = ProcessStatus.STOPPED
            del self.processes[name]
            return True
        
        logger.info(f"Terminating process {name} (PID: {process.pid})")
        process_info.status = ProcessStatus.STOPPING
        
        try:
            # Try graceful termination first
            process.terminate()
            process.join(timeout=timeout)
            
            if process.is_alive():
                # Force kill if still alive
                logger.warning(f"Force killing process {name}")
                process.kill()
                process.join(timeout=2.0)
                
                if process.is_alive():
                    logger.error(f"Failed to kill process {name}")
                    return False
            
            process_info.status = ProcessStatus.STOPPED
            del self.processes[name]
            logger.info(f"Process {name} terminated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error terminating process {name}: {str(e)}")
            return False
    
    def get_process_info(self, name: str) -> Optional[ProcessInfo]:
        """Get information about a process."""
        return self.processes.get(name)
    
    def list_processes(self) -> Dict[str, ProcessInfo]:
        """Get information about all managed processes."""
        return self.processes.copy()
    
    def is_process_running(self, name: str) -> bool:
        """Check if a process is running."""
        process_info = self.processes.get(name)
        return process_info is not None and process_info.is_alive
    
    @handle_exception
    def restart_process(self, name: str) -> bool:
        """
        Restart a process.
        
        Args:
            name: Process name to restart
            
        Returns:
            bool: True if restart was successful
        """
        if name not in self.processes:
            logger.warning(f"Cannot restart unknown process: {name}")
            return False
        
        process_info = self.processes[name]
        config = process_info.config
        
        # Check restart limits
        if (process_info.restart_count >= config.max_restarts and 
            config.max_restarts > 0):
            logger.error(
                f"Process {name} has exceeded maximum restarts "
                f"({config.max_restarts})"
            )
            return False
        
        logger.info(f"Restarting process {name}")
        
        # Terminate existing process
        self.terminate_process(name)
        
        # Wait for restart delay
        if config.restart_delay > 0:
            time.sleep(config.restart_delay)
        
        # Update restart tracking
        config.restart_on_failure = True  # Enable restart for this attempt
        
        try:
            # Spawn new process
            new_process_info = self._spawn_process(config)
            new_process_info.restart_count = process_info.restart_count + 1
            new_process_info.last_restart = time.time()
            
            logger.info(f"Process {name} restarted successfully")
            return True
            
        except ProcessError as e:
            logger.error(f"Failed to restart process {name}: {str(e)}")
            return False
    
    def register_shutdown_handler(self, handler: Callable):
        """
        Register cleanup handler for graceful shutdown.
        
        Args:
            handler: Function to call during shutdown
        """
        self.shutdown_handlers.append(handler)
        logger.debug(f"Registered shutdown handler: {handler.__name__}")
    
    async def start_monitoring(self):
        """Start process monitoring task."""
        if self._monitor_task and not self._monitor_task.done():
            logger.warning("Process monitoring already running")
            return
        
        self._monitor_task = asyncio.create_task(self._monitor_processes())
        logger.info("Process monitoring started")
    
    async def _monitor_processes(self):
        """Monitor processes and handle failures."""
        while not self._shutdown_event.is_set():
            try:
                # Check all processes
                for name, process_info in list(self.processes.items()):
                    if not process_info.is_alive and process_info.status == ProcessStatus.RUNNING:
                        logger.warning(f"Process {name} has died unexpectedly")
                        process_info.status = ProcessStatus.FAILED
                        
                        # Attempt restart if configured
                        if process_info.config.restart_on_failure:
                            logger.info(f"Attempting to restart process {name}")
                            self.restart_process(name)
                
                # Wait before next check
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in process monitoring: {str(e)}")
                await asyncio.sleep(5.0)  # Longer delay on error
    
    async def shutdown(self):
        """Graceful shutdown of all processes."""
        logger.info("Starting graceful shutdown")
        self._shutdown_event.set()
        
        # Stop monitoring
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        # Call shutdown handlers
        for handler in self.shutdown_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                logger.error(f"Error in shutdown handler: {str(e)}")
        
        # Terminate all processes
        await self._terminate_all_processes()
        
        logger.info("Graceful shutdown completed")
    
    async def _terminate_all_processes(self):
        """Terminate all managed processes."""
        if not self.processes:
            return
        
        logger.info(f"Terminating {len(self.processes)} processes")
        
        # Terminate all processes concurrently
        termination_tasks = []
        for name in list(self.processes.keys()):
            task = asyncio.create_task(self._async_terminate_process(name))
            termination_tasks.append(task)
        
        # Wait for all terminations to complete
        if termination_tasks:
            await asyncio.gather(*termination_tasks, return_exceptions=True)
        
        logger.info("All processes terminated")
    
    async def _async_terminate_process(self, name: str):
        """Async wrapper for process termination."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.terminate_process, name)
    
    def cleanup(self):
        """Synchronous cleanup method for non-async contexts."""
        logger.info("Performing synchronous cleanup")
        
        # Terminate all processes synchronously
        for name in list(self.processes.keys()):
            self.terminate_process(name)
        
        logger.info("Synchronous cleanup completed")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information relevant to process management."""
        try:
            return {
                'cpu_count': os.cpu_count(),
                'memory_total': psutil.virtual_memory().total,
                'memory_available': psutil.virtual_memory().available,
                'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None,
                'platform': sys.platform,
                'python_version': sys.version,
                'process_count': len(self.processes),
                'main_process_pid': self.main_process.pid,
            }
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            return {'error': str(e)}
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
    
    def __del__(self):
        """Destructor with cleanup."""
        try:
            self.cleanup()
        except Exception:
            pass  # Ignore errors during cleanup in destructor