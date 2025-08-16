"""
PyElectron Configuration Management

This module provides configuration management with JSON-only persistence
and secure defaults.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pyelectron.utils.errors import ConfigError, handle_exception
from pyelectron.utils.logging import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """
    Configuration management using only JSON - no pickle security risks.
    
    Provides hierarchical configuration with file-based persistence
    and environment variable support.
    """
    
    def __init__(
        self,
        app_name: str = "pyelectron",
        config_file: Optional[Union[str, Path]] = None,
        **default_config
    ):
        """
        Initialize configuration manager.
        
        Args:
            app_name: Application name for default paths
            config_file: Path to configuration file
            **default_config: Default configuration values
        """
        self.app_name = app_name
        self._config: Dict[str, Any] = {}
        
        # Set up config file path
        if config_file:
            self.config_file = Path(config_file)
        else:
            config_dir = Path.home() / '.pyelectron' / app_name
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file = config_dir / 'config.json'
        
        # Load configuration
        self._load_config()
        
        # Apply defaults for missing keys
        for key, value in default_config.items():
            if key not in self._config:
                self._config[key] = value
        
        logger.debug(f"ConfigManager initialized for {app_name}")
    
    @handle_exception
    def _load_config(self):
        """Load configuration from file."""
        if not self.config_file.exists():
            logger.info(f"Config file not found, creating: {self.config_file}")
            self._config = {}
            self._save_config()
            return
        
        try:
            with open(self.config_file, 'r') as f:
                self._config = json.load(f)
            logger.debug(f"Loaded configuration from {self.config_file}")
        except (json.JSONDecodeError, IOError) as e:
            raise ConfigError(
                f"Failed to load configuration from {self.config_file}: {str(e)}",
                details={'config_file': str(self.config_file), 'error': str(e)}
            ) from e
    
    @handle_exception
    def _save_config(self):
        """Save configuration to file."""
        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first
            temp_file = self.config_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self._config, f, indent=2, sort_keys=True)
            
            # Atomic rename
            temp_file.replace(self.config_file)
            logger.debug(f"Saved configuration to {self.config_file}")
            
        except (IOError, OSError) as e:
            raise ConfigError(
                f"Failed to save configuration to {self.config_file}: {str(e)}",
                details={'config_file': str(self.config_file), 'error': str(e)}
            ) from e
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        try:
            # Support dot notation for nested keys
            value = self._config
            for part in key.split('.'):
                value = value[part]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """
        Set configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set (must be JSON serializable)
        """
        # Validate JSON serializable
        try:
            json.dumps(value)
        except (TypeError, ValueError) as e:
            raise ConfigError(
                f"Configuration value must be JSON serializable: {str(e)}",
                details={'key': key, 'value_type': type(value).__name__}
            ) from e
        
        # Support dot notation for nested keys
        config = self._config
        parts = key.split('.')
        
        # Navigate to parent
        for part in parts[:-1]:
            if part not in config:
                config[part] = {}
            elif not isinstance(config[part], dict):
                raise ConfigError(
                    f"Cannot set nested key '{key}': parent is not a dict",
                    details={'key': key, 'parent_key': part}
                )
            config = config[part]
        
        # Set value
        config[parts[-1]] = value
        
        # Save to file
        self._save_config()
        logger.debug(f"Set configuration: {key} = {value}")
    
    def delete(self, key: str) -> bool:
        """
        Delete configuration key.
        
        Args:
            key: Configuration key to delete
            
        Returns:
            bool: True if key was deleted, False if not found
        """
        try:
            # Support dot notation
            config = self._config
            parts = key.split('.')
            
            # Navigate to parent
            for part in parts[:-1]:
                config = config[part]
            
            # Delete key
            del config[parts[-1]]
            
            # Save to file
            self._save_config()
            logger.debug(f"Deleted configuration key: {key}")
            return True
            
        except (KeyError, TypeError):
            return False
    
    def has(self, key: str) -> bool:
        """
        Check if configuration key exists.
        
        Args:
            key: Configuration key to check
            
        Returns:
            bool: True if key exists
        """
        try:
            config = self._config
            for part in key.split('.'):
                config = config[part]
            return True
        except (KeyError, TypeError):
            return False
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as a dictionary."""
        return self._config.copy()
    
    def update(self, config: Dict[str, Any]):
        """
        Update configuration with dictionary.
        
        Args:
            config: Dictionary of configuration values
        """
        # Validate all values are JSON serializable
        try:
            json.dumps(config)
        except (TypeError, ValueError) as e:
            raise ConfigError(
                f"Configuration values must be JSON serializable: {str(e)}",
                details={'config_keys': list(config.keys())}
            ) from e
        
        # Deep update
        self._deep_update(self._config, config)
        
        # Save to file
        self._save_config()
        logger.debug(f"Updated configuration with {len(config)} keys")
    
    def _deep_update(self, target: Dict[str, Any], source: Dict[str, Any]):
        """Deep update dictionary."""
        for key, value in source.items():
            if (key in target and 
                isinstance(target[key], dict) and 
                isinstance(value, dict)):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    def reset(self):
        """Reset configuration to empty state."""
        self._config = {}
        self._save_config()
        logger.info("Configuration reset to empty state")
    
    def reload(self):
        """Reload configuration from file."""
        self._load_config()
        logger.info("Configuration reloaded from file")
    
    def export_config(self, file_path: Union[str, Path]):
        """
        Export configuration to file.
        
        Args:
            file_path: Path to export configuration
        """
        export_path = Path(file_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(export_path, 'w') as f:
            json.dump(self._config, f, indent=2, sort_keys=True)
        
        logger.info(f"Configuration exported to {export_path}")
    
    def import_config(self, file_path: Union[str, Path]):
        """
        Import configuration from file.
        
        Args:
            file_path: Path to import configuration from
        """
        import_path = Path(file_path)
        
        if not import_path.exists():
            raise ConfigError(
                f"Import file does not exist: {import_path}",
                details={'file_path': str(import_path)}
            )
        
        try:
            with open(import_path, 'r') as f:
                imported_config = json.load(f)
            
            self.update(imported_config)
            logger.info(f"Configuration imported from {import_path}")
            
        except (json.JSONDecodeError, IOError) as e:
            raise ConfigError(
                f"Failed to import configuration: {str(e)}",
                details={'file_path': str(import_path), 'error': str(e)}
            ) from e
    
    def __getitem__(self, key: str) -> Any:
        """Dictionary-style access for getting values."""
        value = self.get(key)
        if value is None and key not in self._config:
            raise KeyError(key)
        return value
    
    def __setitem__(self, key: str, value: Any):
        """Dictionary-style access for setting values."""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """Dictionary-style membership testing."""
        return self.has(key)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"ConfigManager(app='{self.app_name}', keys={len(self._config)})"