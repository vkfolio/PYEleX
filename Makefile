# PyElectron Development Makefile

.PHONY: help install install-dev clean test lint format type-check security docs build package

# Default target
help:
	@echo "PyElectron Development Commands:"
	@echo ""
	@echo "Setup:"
	@echo "  install      Install PyElectron in development mode"
	@echo "  install-dev  Install development dependencies"
	@echo "  clean        Clean build artifacts and cache"
	@echo ""
	@echo "Development:"
	@echo "  test         Run test suite"
	@echo "  test-fast    Run tests without slow/integration tests"
	@echo "  lint         Run all linting checks"
	@echo "  format       Format code with black and isort"
	@echo "  type-check   Run type checking with mypy"
	@echo "  security     Run security scans"
	@echo ""
	@echo "Documentation:"
	@echo "  docs         Build documentation"
	@echo "  docs-serve   Serve documentation locally"
	@echo ""
	@echo "Build:"
	@echo "  build        Build package for distribution"
	@echo "  package      Create platform-specific packages"

# Setup targets
install:
	pip install -e .

install-dev:
	pip install -r requirements-dev.txt
	pip install -e .
	pre-commit install

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf site/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.orig" -delete
	find . -type f -name "*.rej" -delete

# Development targets
test:
	pytest tests/ -v --cov=pyelectron --cov-report=html --cov-report=term-missing

test-fast:
	pytest tests/ -v -m "not slow and not integration"

test-integration:
	pytest tests/integration/ -v

lint: 
	flake8 pyelectron tests
	black --check pyelectron tests
	isort --check-only pyelectron tests
	pydocstyle pyelectron

format:
	black pyelectron tests
	isort pyelectron tests

type-check:
	mypy pyelectron --ignore-missing-imports

security:
	bandit -r pyelectron -f json -o bandit-report.json
	safety check -r requirements.txt -r requirements-dev.txt

# Documentation targets
docs:
	mkdocs build

docs-serve:
	mkdocs serve

# Build targets
build:
	python -m build

package:
	python -m build
	# Platform-specific packaging would go here

# Development workflow
dev-setup: install-dev
	@echo "Development environment ready!"
	@echo "Run 'make test' to run tests"
	@echo "Run 'make lint' to check code quality"

# CI targets (used by GitHub Actions)
ci-test: test lint type-check security

# Release targets
version-check:
	@python -c "import pyelectron; print(f'Version: {pyelectron.__version__}')"

pre-release: clean lint type-check test security docs build
	@echo "Pre-release checks passed!"

# Platform-specific targets
install-platform-deps:
	@echo "Installing platform-specific dependencies..."
	@if [ "$(shell uname)" = "Darwin" ]; then \
		pip install "pyobjc-framework-WebKit>=9.0.0" "pyobjc-framework-Cocoa>=9.0.0"; \
	elif [ "$(shell uname)" = "Linux" ]; then \
		pip install "PyGObject>=3.42.0"; \
	elif [ "$(shell uname | grep -i cygwin)" ]; then \
		pip install "pywebview[cef]>=4.0.0"; \
	fi
	@echo "Platform dependencies installed"

# Example targets
run-examples:
	@echo "Running example applications..."
	cd examples && python hello_world.py

# Performance targets
benchmark:
	pytest tests/performance/ -v --benchmark-only

profile:
	python -m cProfile -o profile.stats -m pyelectron.cli.main --help
	@echo "Profile saved to profile.stats"