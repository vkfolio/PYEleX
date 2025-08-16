"""
Unit tests for PyElectron process management

Tests the ProcessManager, ProcessConfig, and related functionality.
"""

import asyncio
import multiprocessing
import os
import signal
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyelectron.core.process import (
    ProcessManager,
    ProcessConfig,
    ProcessType,
    ProcessStatus,
    ProcessInfo,
)
from pyelectron.utils.errors import ProcessError


class TestProcessConfig:
    """Test ProcessConfig data class."""
    
    def test_process_config_basic(self):
        """Test basic ProcessConfig creation."""
        config = ProcessConfig(
            type=ProcessType.WORKER,
            name="test_worker",
            target=lambda: None
        )
        
        assert config.type == ProcessType.WORKER
        assert config.name == "test_worker"
        assert config.target is not None
        assert config.daemon is True  # Default
        assert config.restart_on_failure is False  # Default
    
    def test_process_config_with_options(self):
        """Test ProcessConfig with custom options."""
        def dummy_target():
            pass
        
        config = ProcessConfig(
            type=ProcessType.RENDERER,
            name="test_renderer",
            target=dummy_target,
            args=(1, 2, 3),
            kwargs={'key': 'value'},
            daemon=False,
            restart_on_failure=True,
            max_restarts=5,
            timeout=60.0
        )
        
        assert config.type == ProcessType.RENDERER
        assert config.args == (1, 2, 3)
        assert config.kwargs == {'key': 'value'}
        assert config.daemon is False
        assert config.restart_on_failure is True
        assert config.max_restarts == 5
        assert config.timeout == 60.0
    
    def test_process_config_validation_main_process(self):
        """Test that main process type doesn't require target."""
        config = ProcessConfig(
            type=ProcessType.MAIN,
            name="main"
        )
        # Should not raise exception
        assert config.type == ProcessType.MAIN
    
    def test_process_config_validation_worker_without_target(self):
        """Test that worker process requires target."""
        with pytest.raises(ProcessError) as exc_info:
            ProcessConfig(
                type=ProcessType.WORKER,
                name="worker"
                # Missing target
            )
        
        assert "Process target is required" in str(exc_info.value)
        assert "worker" in str(exc_info.value)


class TestProcessInfo:
    """Test ProcessInfo data class."""
    
    def test_process_info_creation(self):
        """Test ProcessInfo creation."""
        config = ProcessConfig(
            type=ProcessType.WORKER,
            name="test",
            target=lambda: None
        )
        
        mock_process = MagicMock()
        mock_process.is_alive.return_value = True
        
        info = ProcessInfo(
            config=config,
            process=mock_process,
            status=ProcessStatus.RUNNING,
            pid=12345,
            started_at=time.time()
        )
        
        assert info.config == config
        assert info.process == mock_process
        assert info.status == ProcessStatus.RUNNING
        assert info.pid == 12345
        assert info.is_alive is True
        assert info.uptime is not None
        assert info.uptime > 0
    
    def test_process_info_uptime_not_running(self):
        """Test uptime when process is not running."""
        config = ProcessConfig(
            type=ProcessType.WORKER,
            name="test",
            target=lambda: None
        )
        
        mock_process = MagicMock()
        
        info = ProcessInfo(
            config=config,
            process=mock_process,
            status=ProcessStatus.STOPPED
        )
        
        assert info.uptime is None


class TestProcessManager:
    """Test ProcessManager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ProcessManager()
    
    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'manager'):
            self.manager.cleanup()
    
    def test_process_manager_initialization(self):
        """Test ProcessManager initialization."""
        assert isinstance(self.manager.processes, dict)
        assert len(self.manager.processes) == 0
        assert isinstance(self.manager.shutdown_handlers, list)
        assert self.manager.main_process == multiprocessing.current_process()
    
    def dummy_worker_function(self, duration=0.1):
        """Dummy function for worker processes."""
        time.sleep(duration)
        return "completed"
    
    def test_spawn_worker_basic(self):
        """Test basic worker spawning."""
        process_info = self.manager.spawn_worker(
            "test_worker",
            self.dummy_worker_function,
            (0.1,)
        )
        
        assert isinstance(process_info, ProcessInfo)
        assert process_info.config.name == "test_worker"
        assert process_info.config.type == ProcessType.WORKER
        assert process_info.status == ProcessStatus.RUNNING
        assert process_info.pid is not None
        assert process_info.is_alive
        
        # Clean up
        self.manager.terminate_process("test_worker")
    
    def test_spawn_worker_duplicate_name(self):
        """Test spawning worker with duplicate name."""
        # Spawn first worker
        self.manager.spawn_worker(
            "duplicate_worker",
            self.dummy_worker_function,
            (0.1,)
        )
        
        # Spawn second worker with same name (should terminate first)
        process_info = self.manager.spawn_worker(
            "duplicate_worker",
            self.dummy_worker_function,
            (0.1,)
        )
        
        assert isinstance(process_info, ProcessInfo)
        assert len(self.manager.processes) == 1
        
        # Clean up
        self.manager.terminate_process("duplicate_worker")
    
    def test_spawn_renderer(self):
        """Test renderer process spawning."""
        process_info = self.manager.spawn_renderer(
            "test_renderer",
            self.dummy_worker_function,
            (0.1,)
        )
        
        assert isinstance(process_info, ProcessInfo)
        assert process_info.config.type == ProcessType.RENDERER
        assert process_info.config.daemon is False  # Renderers should not be daemon
        
        # Clean up
        self.manager.terminate_process("test_renderer")
    
    def test_terminate_process(self):
        """Test process termination."""
        # Spawn a worker
        self.manager.spawn_worker(
            "termination_test",
            self.dummy_worker_function,
            (1.0,)  # Longer duration
        )
        
        assert "termination_test" in self.manager.processes
        assert self.manager.is_process_running("termination_test")
        
        # Terminate the process
        result = self.manager.terminate_process("termination_test")
        
        assert result is True
        assert "termination_test" not in self.manager.processes
        assert not self.manager.is_process_running("termination_test")
    
    def test_terminate_nonexistent_process(self):
        """Test terminating non-existent process."""
        result = self.manager.terminate_process("nonexistent")
        assert result is False
    
    def test_get_process_info(self):
        """Test getting process information."""
        # Test non-existent process
        info = self.manager.get_process_info("nonexistent")
        assert info is None
        
        # Spawn and test existing process
        self.manager.spawn_worker(
            "info_test",
            self.dummy_worker_function,
            (0.5,)
        )
        
        info = self.manager.get_process_info("info_test")
        assert isinstance(info, ProcessInfo)
        assert info.config.name == "info_test"
        
        # Clean up
        self.manager.terminate_process("info_test")
    
    def test_list_processes(self):
        """Test listing all processes."""
        # Initially empty
        processes = self.manager.list_processes()
        assert len(processes) == 0
        
        # Spawn some processes
        self.manager.spawn_worker("worker1", self.dummy_worker_function, (0.5,))
        self.manager.spawn_worker("worker2", self.dummy_worker_function, (0.5,))
        
        processes = self.manager.list_processes()
        assert len(processes) == 2
        assert "worker1" in processes
        assert "worker2" in processes
        
        # Clean up
        self.manager.terminate_process("worker1")
        self.manager.terminate_process("worker2")
    
    def test_register_shutdown_handler(self):
        """Test registering shutdown handlers."""
        def dummy_handler():
            pass
        
        initial_count = len(self.manager.shutdown_handlers)
        self.manager.register_shutdown_handler(dummy_handler)
        
        assert len(self.manager.shutdown_handlers) == initial_count + 1
        assert dummy_handler in self.manager.shutdown_handlers
    
    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """Test process monitoring."""
        await self.manager.start_monitoring()
        
        assert self.manager._monitor_task is not None
        assert not self.manager._monitor_task.done()
        
        # Stop monitoring
        self.manager._shutdown_event.set()
        await asyncio.sleep(0.1)  # Give time for monitoring to stop
    
    def failing_worker_function(self):
        """Worker function that fails immediately."""
        raise RuntimeError("Intentional failure")
    
    def test_restart_process(self):
        """Test process restart functionality."""
        # Spawn a process with restart enabled
        config = ProcessConfig(
            type=ProcessType.WORKER,
            name="restart_test",
            target=self.dummy_worker_function,
            args=(0.1,),
            restart_on_failure=True,
            max_restarts=2
        )
        
        self.manager._spawn_process(config)
        original_pid = self.manager.processes["restart_test"].pid
        
        # Restart the process
        result = self.manager.restart_process("restart_test")
        
        assert result is True
        assert "restart_test" in self.manager.processes
        
        # Should have new PID
        new_info = self.manager.get_process_info("restart_test")
        assert new_info.restart_count == 1
        
        # Clean up
        self.manager.terminate_process("restart_test")
    
    def test_restart_nonexistent_process(self):
        """Test restarting non-existent process."""
        result = self.manager.restart_process("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test graceful shutdown."""
        # Spawn some processes
        self.manager.spawn_worker("shutdown_test1", self.dummy_worker_function, (1.0,))
        self.manager.spawn_worker("shutdown_test2", self.dummy_worker_function, (1.0,))
        
        assert len(self.manager.processes) == 2
        
        # Start monitoring
        await self.manager.start_monitoring()
        
        # Shutdown
        await self.manager.shutdown()
        
        # All processes should be terminated
        assert len(self.manager.processes) == 0
        assert self.manager._shutdown_event.is_set()
    
    def test_context_manager(self):
        """Test ProcessManager as context manager."""
        with ProcessManager() as manager:
            manager.spawn_worker("context_test", self.dummy_worker_function, (0.1,))
            assert "context_test" in manager.processes
        
        # Should be cleaned up automatically
        assert len(manager.processes) == 0
    
    def test_get_system_info(self):
        """Test system information gathering."""
        info = self.manager.get_system_info()
        
        assert isinstance(info, dict)
        assert 'cpu_count' in info
        assert 'memory_total' in info
        assert 'memory_available' in info
        assert 'platform' in info
        assert 'python_version' in info
        assert 'process_count' in info
        assert 'main_process_pid' in info
        
        assert info['process_count'] == len(self.manager.processes)
        assert info['main_process_pid'] == self.manager.main_process.pid


class TestProcessLifecycle:
    """Test process lifecycle and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ProcessManager()
    
    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'manager'):
            self.manager.cleanup()
    
    def long_running_worker(self, duration=10):
        """Long-running worker for testing."""
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(0.1)
        return "completed"
    
    def test_process_kill_if_terminate_fails(self):
        """Test force kill if graceful termination fails."""
        # Spawn long-running process
        self.manager.spawn_worker(
            "stubborn_worker",
            self.long_running_worker,
            (5.0,)
        )
        
        process_info = self.manager.get_process_info("stubborn_worker")
        original_process = process_info.process
        
        # Mock terminate to do nothing (simulate unresponsive process)
        with patch.object(original_process, 'terminate'):
            with patch.object(original_process, 'is_alive', return_value=True):
                # This should fall back to kill
                result = self.manager.terminate_process("stubborn_worker", timeout=0.1)
                assert result is True
    
    def test_error_handling_in_process_wrapper(self):
        """Test error handling in process wrapper."""
        def failing_function():
            raise ValueError("Test error")
        
        # This should not crash the main process
        process_info = self.manager.spawn_worker(
            "failing_worker",
            failing_function
        )
        
        # Give process time to fail
        time.sleep(0.5)
        
        # Process should have failed but manager should be fine
        assert "failing_worker" in self.manager.processes


@pytest.mark.integration
class TestProcessIntegration:
    """Integration tests for process management."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ProcessManager()
    
    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, 'manager'):
            self.manager.cleanup()
    
    def worker_with_shared_state(self, shared_dict, key, value):
        """Worker that modifies shared state."""
        shared_dict[key] = value
        time.sleep(0.1)
        return value
    
    def test_multiple_workers_with_shared_state(self):
        """Test multiple workers with shared state."""
        import multiprocessing
        
        # Create shared dictionary
        manager_mp = multiprocessing.Manager()
        shared_dict = manager_mp.dict()
        
        # Spawn multiple workers
        workers = []
        for i in range(3):
            process_info = self.manager.spawn_worker(
                f"shared_worker_{i}",
                self.worker_with_shared_state,
                (shared_dict, f"key_{i}", f"value_{i}")
            )
            workers.append(process_info)
        
        # Wait for workers to complete
        time.sleep(1.0)
        
        # Check shared state
        assert len(shared_dict) == 3
        for i in range(3):
            assert shared_dict[f"key_{i}"] == f"value_{i}"
        
        # Clean up
        for i in range(3):
            self.manager.terminate_process(f"shared_worker_{i}")
    
    @pytest.mark.asyncio
    async def test_monitoring_with_process_failures(self):
        """Test monitoring with process failures and restarts."""
        def failing_then_succeeding_worker(attempt_file):
            """Worker that fails first time, succeeds second time."""
            if not os.path.exists(attempt_file):
                # First attempt - create file and fail
                Path(attempt_file).touch()
                raise RuntimeError("First attempt failure")
            else:
                # Second attempt - succeed
                time.sleep(0.1)
                return "success"
        
        import tempfile
        attempt_file = tempfile.mktemp()
        
        try:
            # Configure worker with restart
            config = ProcessConfig(
                type=ProcessType.WORKER,
                name="failure_test",
                target=failing_then_succeeding_worker,
                args=(attempt_file,),
                restart_on_failure=True,
                max_restarts=2,
                restart_delay=0.1
            )
            
            # Start monitoring
            await self.manager.start_monitoring()
            
            # Spawn the worker
            self.manager._spawn_process(config)
            
            # Give time for failure and restart
            await asyncio.sleep(2.0)
            
            # Worker should have been restarted
            process_info = self.manager.get_process_info("failure_test")
            if process_info:
                assert process_info.restart_count >= 1
            
            # Stop monitoring
            self.manager._shutdown_event.set()
            await asyncio.sleep(0.1)
            
        finally:
            # Clean up
            if os.path.exists(attempt_file):
                os.unlink(attempt_file)
            if "failure_test" in self.manager.processes:
                self.manager.terminate_process("failure_test")