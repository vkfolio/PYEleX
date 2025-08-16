"""
PyElectron State Manager

This module provides secure JSON-only state persistence
without the security risks of pickle serialization.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional, Dict

import aiofiles

from pyelectron.utils.errors import StateError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class StateManager:
    """
    State management using only JSON - no pickle security risks.
    
    Provides persistent state storage with automatic batching
    and crash recovery.
    """
    
    def __init__(self, app_name: str = "pyelectron"):
        """
        Initialize state manager.
        
        Args:
            app_name: Application name for state directory
        """
        self.app_name = app_name
        self.state_dir = Path.home() / '.pyelectron' / app_name / 'state'
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self.cache: Dict[str, Any] = {}
        self.dirty: set[str] = set()
        
        # Background persistence
        self.persist_task: Optional[asyncio.Task] = None
        self.is_initialized = False
        
        logger.debug(f"StateManager initialized for {app_name}")
    
    @handle_exception
    async def initialize(self):
        """Initialize state manager."""
        if self.is_initialized:
            return
        
        logger.info("Initializing StateManager")
        self.is_initialized = True
        logger.info("StateManager initialized")
    
    @handle_exception
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get state value.
        
        Args:
            key: State key
            default: Default value if not found
            
        Returns:
            State value
        """
        # Check cache first
        if key in self.cache:
            return self.cache[key]
        
        # Load from disk
        file_path = self.state_dir / f"{key}.json"
        if file_path.exists():
            try:
                async with aiofiles.open(file_path, 'r') as f:
                    data = await f.read()
                    value = json.loads(data)
                    self.cache[key] = value
                    return value
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load state {key}: {e}")
        
        return default
    
    @handle_exception
    async def set(self, key: str, value: Any):
        """
        Set state value - JSON serializable only.
        
        Args:
            key: State key
            value: Value to store (must be JSON serializable)
        """
        # Validate JSON serializable
        try:
            json.dumps(value)
        except (TypeError, ValueError) as e:
            raise StateError(
                f"State value must be JSON serializable: {str(e)}",
                details={'key': key, 'value_type': type(value).__name__}
            ) from e
        
        # Update cache
        self.cache[key] = value
        self.dirty.add(key)
        
        # Schedule persistence
        if not self.persist_task or self.persist_task.done():
            self.persist_task = asyncio.create_task(self._persist_dirty())
    
    @handle_exception
    async def delete(self, key: str) -> bool:
        """
        Delete state key.
        
        Args:
            key: State key to delete
            
        Returns:
            bool: True if key was deleted
        """
        # Remove from cache
        if key in self.cache:
            del self.cache[key]
        
        # Remove from dirty set
        self.dirty.discard(key)
        
        # Remove file
        file_path = self.state_dir / f"{key}.json"
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted state file: {key}")
            return True
        
        return False
    
    async def _persist_dirty(self):
        """Persist dirty state to disk."""
        await asyncio.sleep(0.1)  # Batch writes
        
        for key in list(self.dirty):
            file_path = self.state_dir / f"{key}.json"
            temp_path = file_path.with_suffix('.tmp')
            
            try:
                # Write to temp file
                async with aiofiles.open(temp_path, 'w') as f:
                    await f.write(json.dumps(self.cache[key], indent=2))
                
                # Atomic rename
                temp_path.replace(file_path)
                self.dirty.discard(key)
                
            except Exception as e:
                logger.error(f"Failed to persist {key}: {e}")
                if temp_path.exists():
                    temp_path.unlink()
    
    async def cleanup(self):
        """Cleanup state manager."""
        logger.info("Cleaning up StateManager")
        
        # Persist any remaining dirty state
        if self.dirty:
            await self._persist_dirty()
        
        # Cancel persistence task
        if self.persist_task and not self.persist_task.done():
            self.persist_task.cancel()
            try:
                await self.persist_task
            except asyncio.CancelledError:
                pass
        
        logger.info("StateManager cleanup completed")