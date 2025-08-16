"""
PyElectron test configuration and fixtures

This module provides shared test fixtures, configuration,
and utilities for the entire test suite.
"""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import Generator, Any
import pytest

# Set test environment variable
os.environ["PYELECTRON_TEST_MODE"] = "1"

# Import PyElectron components after setting test mode
import pyelectron
from pyelectron.core.app import PyElectronApp
from pyelectron.core.process import ProcessManager
from pyelectron.state.manager import StateManager
from pyelectron.utils.logging import get_logger


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    temp_dir = Path(tempfile.mkdtemp(prefix="pyelectron_test_"))
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def app_config(temp_dir: Path) -> dict:
    """Basic application configuration for testing."""
    return {
        "name": "TestApp",
        "data_dir": temp_dir / "data",
        "log_level": "DEBUG",
        "development_mode": True,
    }


@pytest.fixture
async def test_app(app_config: dict) -> Generator[PyElectronApp, None, None]:
    """Create a test PyElectron application instance."""
    app = PyElectronApp(**app_config)
    
    # Initialize but don't start fully (no WebView in tests)
    await app._initialize_basic()
    
    try:
        yield app
    finally:
        await app.cleanup()


@pytest.fixture
def process_manager() -> Generator[ProcessManager, None, None]:
    """Create a test process manager."""
    manager = ProcessManager()
    try:
        yield manager
    finally:
        manager.cleanup()


@pytest.fixture
async def state_manager(temp_dir: Path) -> Generator[StateManager, None, None]:
    """Create a test state manager."""
    manager = StateManager(app_name="test_app")
    manager.state_dir = temp_dir / "state"
    manager.state_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        yield manager
    finally:
        await manager.cleanup()


@pytest.fixture
def logger():
    """Get a test logger instance."""
    return get_logger("test", level="DEBUG")


@pytest.fixture
def mock_webview_available(monkeypatch):
    """Mock WebView availability for testing."""
    def mock_check():
        return True, "Mock WebView available"
    
    monkeypatch.setattr(pyelectron, "check_webview_availability", mock_check)


@pytest.fixture(scope="session")
def platform_info():
    """Get platform information for testing."""
    return pyelectron.get_platform_info()


class TestHelper:
    """Helper class for common test operations."""
    
    @staticmethod
    def create_test_file(path: Path, content: str = "test content") -> Path:
        """Create a test file with given content."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path
    
    @staticmethod
    def create_test_json_file(path: Path, data: dict) -> Path:
        """Create a test JSON file with given data."""
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        return path
    
    @staticmethod
    async def wait_for_condition(
        condition_func, 
        timeout: float = 5.0, 
        interval: float = 0.1
    ) -> bool:
        """Wait for a condition to become true."""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if condition_func():
                return True
            await asyncio.sleep(interval)
        
        return False


@pytest.fixture
def test_helper():
    """Get test helper instance."""
    return TestHelper()


# Pytest markers
pytest_mark_slow = pytest.mark.slow
pytest_mark_integration = pytest.mark.integration
pytest_mark_platform = pytest.mark.platform
pytest_mark_gui = pytest.mark.gui


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "platform: mark test as platform-specific")
    config.addinivalue_line("markers", "gui: mark test as requiring GUI")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    # Add 'slow' marker to tests that take >5 seconds
    # Add 'integration' marker to tests in integration/ directory
    # Add 'gui' marker to tests that require GUI interaction
    
    for item in items:
        # Mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Mark GUI tests
        if "webview" in str(item.fspath) or "gui" in item.name.lower():
            item.add_marker(pytest.mark.gui)
        
        # Mark performance tests as slow
        if "performance" in str(item.fspath) or "benchmark" in item.name:
            item.add_marker(pytest.mark.slow)


# Skip GUI tests if running in headless environment
def pytest_runtest_setup(item):
    """Setup individual test runs."""
    if item.get_closest_marker("gui"):
        if os.environ.get("CI") or not os.environ.get("DISPLAY"):
            pytest.skip("GUI test skipped in headless environment")


# Custom assertions
def assert_file_exists(path: Path, message: str = ""):
    """Assert that a file exists."""
    assert path.exists(), f"File does not exist: {path} {message}"


def assert_file_contains(path: Path, content: str, message: str = ""):
    """Assert that a file contains specific content."""
    assert_file_exists(path)
    file_content = path.read_text()
    assert content in file_content, f"File does not contain '{content}': {path} {message}"


def assert_json_file_contains(path: Path, key: str, expected_value: Any, message: str = ""):
    """Assert that a JSON file contains a specific key-value pair."""
    import json
    assert_file_exists(path)
    
    with open(path) as f:
        data = json.load(f)
    
    assert key in data, f"JSON file missing key '{key}': {path} {message}"
    assert data[key] == expected_value, f"JSON key '{key}' has wrong value: {path} {message}"


# Add custom assertions to pytest namespace
pytest.assert_file_exists = assert_file_exists
pytest.assert_file_contains = assert_file_contains
pytest.assert_json_file_contains = assert_json_file_contains