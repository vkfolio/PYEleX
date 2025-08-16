"""
Setup script for PyElectron

This file provides backward compatibility for older pip versions
that don't support PEP 517/518. The actual configuration is in pyproject.toml.
"""

from setuptools import setup

if __name__ == "__main__":
    setup()