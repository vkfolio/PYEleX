"""
State management modules

This package provides secure JSON-only state persistence
without the security risks of pickle serialization.
"""

from pyelectron.state.manager import StateManager

__all__ = [
    "StateManager",
]