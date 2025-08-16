# Contributing to PyElectron

Thank you for your interest in contributing to PyElectron! We welcome contributions from everyone, whether you're fixing a bug, adding a feature, improving documentation, or helping with testing.

## 🎯 Project Goals

Before contributing, please understand PyElectron's goals:

- **Python-Native**: Best desktop framework for Python developers
- **Simplicity**: Simple, reliable solutions over complex ones
- **Realistic**: Achievable performance targets, not impossible ones
- **Security**: Secure by default, not complex security theater

## 🚀 Getting Started

### Development Environment Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/YOUR_USERNAME/pyelectron.git
   cd pyelectron
   ```

2. **Set up Development Environment**
   ```bash
   # Install development dependencies
   make dev-setup
   
   # Or manually:
   pip install -r requirements-dev.txt
   pip install -e .
   pre-commit install
   ```

3. **Verify Setup**
   ```bash
   # Run tests to ensure everything works
   make test
   
   # Check code quality
   make lint
   ```

### Development Workflow

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-number
   ```

2. **Make Changes**
   - Write code following our [coding standards](#coding-standards)
   - Add tests for new functionality
   - Update documentation if needed

3. **Test Your Changes**
   ```bash
   # Run full test suite
   make test
   
   # Run fast tests during development
   make test-fast
   
   # Check code quality
   make lint
   
   # Format code
   make format
   ```

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: add amazing new feature"
   ```

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a Pull Request on GitHub.

## 📋 Contribution Types

### 🐛 Bug Reports

Before creating a bug report:
- Check if the issue already exists
- Try to reproduce with a minimal example
- Test on the latest version

**Bug Report Template:**
```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. See error

**Expected behavior**
What you expected to happen.

**Environment:**
- OS: [e.g. Windows 10, macOS 12.0, Ubuntu 20.04]
- Python version: [e.g. 3.9.7]
- PyElectron version: [e.g. 0.1.0-alpha.1]

**Additional context**
Any other context about the problem.
```

### 💡 Feature Requests

For feature requests:
- Check if it aligns with project goals
- Explain the use case and benefits
- Consider if it can be implemented as a plugin

**Feature Request Template:**
```markdown
**Is your feature request related to a problem?**
A clear description of what the problem is.

**Describe the solution you'd like**
A clear description of what you want to happen.

**Describe alternatives you've considered**
Other solutions you've considered.

**Additional context**
Any other context about the feature request.
```

### 🔧 Code Contributions

#### Areas We Need Help With

1. **Core Framework**
   - Process management improvements
   - IPC performance optimization
   - WebView integration fixes

2. **Platform Support**
   - Linux distribution testing
   - Windows WebView2 edge cases
   - macOS compatibility improvements

3. **Developer Tools**
   - Hot reload reliability
   - Debugging integration
   - Performance profiling

4. **Documentation**
   - API documentation
   - Tutorial creation
   - Example applications

5. **Testing**
   - Cross-platform testing
   - Performance benchmarks
   - Integration test coverage

## 🎨 Coding Standards

### Python Code Style

We use [Black](https://black.readthedocs.io/) for code formatting with these settings:
- Line length: 88 characters
- Target Python versions: 3.8+

```bash
# Format code
black pyelectron tests

# Check formatting
black --check pyelectron tests
```

### Import Organization

We use [isort](https://pycqa.github.io/isort/) with Black profile:

```bash
# Sort imports
isort pyelectron tests

# Check import sorting
isort --check-only pyelectron tests
```

### Type Hints

- Use type hints for all public APIs
- Use `typing` module for complex types
- Run mypy for type checking

```python
from typing import Optional, List, Dict, Any

async def process_data(
    data: List[Dict[str, Any]], 
    options: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Process data with optional configuration."""
    pass
```

### Documentation

- Use Google-style docstrings
- Document all public functions and classes
- Include examples for complex APIs

```python
def create_window(config: WindowConfig) -> WindowHandle:
    """Create a new application window.
    
    Args:
        config: Window configuration options including size, title, etc.
        
    Returns:
        WindowHandle: Handle to the created window.
        
    Raises:
        WebViewError: If window creation fails.
        
    Example:
        >>> config = WindowConfig(width=800, height=600, title="My App")
        >>> window = create_window(config)
    """
    pass
```

### Error Handling

- Use PyElectron custom exceptions
- Provide clear, actionable error messages
- Include context in error details

```python
from pyelectron.utils.errors import WebViewError

def load_url(url: str):
    if not url.startswith(('http://', 'https://')):
        raise WebViewError(
            f"Invalid URL scheme: {url}",
            details={'url': url, 'expected_schemes': ['http', 'https']}
        )
```

### Testing Requirements

- Write tests for all new functionality
- Aim for >90% test coverage
- Use descriptive test names
- Include both positive and negative test cases

```python
class TestWindowManager:
    """Test window management functionality."""
    
    async def test_create_window_with_valid_config(self):
        """Test creating window with valid configuration succeeds."""
        # Test implementation
        pass
    
    async def test_create_window_with_invalid_config_raises_error(self):
        """Test creating window with invalid config raises appropriate error."""
        # Test implementation
        pass
```

## 🧪 Testing Guidelines

### Test Categories

1. **Unit Tests** (`tests/unit/`)
   - Test individual functions/classes in isolation
   - Fast execution (<1s per test)
   - No external dependencies

2. **Integration Tests** (`tests/integration/`)
   - Test component interactions
   - May take longer to execute
   - Can use real WebView/IPC

3. **Performance Tests** (`tests/performance/`)
   - Benchmark critical functionality
   - Monitor performance regressions
   - Marked as `@pytest.mark.slow`

### Running Tests

```bash
# All tests
make test

# Fast tests only
make test-fast

# Specific test file
pytest tests/unit/test_window.py -v

# Tests with coverage
pytest --cov=pyelectron --cov-report=html

# Performance tests
pytest tests/performance/ --benchmark-only
```

### Test Fixtures

Use the provided fixtures in `conftest.py`:

```python
async def test_app_creation(test_app):
    """Test app creation using the test_app fixture."""
    assert test_app.name == "TestApp"
    assert test_app.is_initialized
```

## 📖 Documentation

### Types of Documentation

1. **API Documentation**: Auto-generated from docstrings
2. **Tutorials**: Step-by-step guides for common tasks
3. **Examples**: Complete example applications
4. **Architecture**: Technical design documentation

### Building Documentation

```bash
# Build documentation
make docs

# Serve documentation locally
make docs-serve
```

### Documentation Standards

- Use clear, concise language
- Include code examples
- Test all code examples
- Update when APIs change

## 🔍 Code Review Process

### What We Look For

1. **Functionality**: Does it work as intended?
2. **Tests**: Are there adequate tests?
3. **Documentation**: Is it properly documented?
4. **Performance**: Does it meet performance requirements?
5. **Security**: Are there security implications?
6. **Style**: Does it follow coding standards?

### Review Guidelines

**For Contributors:**
- Respond to feedback promptly
- Make requested changes
- Ask questions if unclear
- Test thoroughly before requesting review

**For Reviewers:**
- Be constructive and helpful
- Explain the reasoning behind suggestions
- Approve when ready
- Test changes when possible

## 🏷️ Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or modifying tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(ipc): add shared memory support for large data transfer

fix(webview): resolve crash on window resize in Linux

docs: add tutorial for data science applications

test: increase coverage for process management
```

## 🚀 Release Process

### Version Numbering

We use [Semantic Versioning](https://semver.org/):
- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Types

- **Alpha**: Early development, may have bugs
- **Beta**: Feature complete, testing phase
- **RC**: Release candidate, final testing
- **Stable**: Production ready

### Release Checklist

- [ ] All tests pass
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] Version bumped
- [ ] Security scan passed
- [ ] Performance benchmarks acceptable

## 🆘 Getting Help

### Where to Get Help

1. **GitHub Discussions**: General questions and discussions
2. **GitHub Issues**: Bug reports and feature requests
3. **Documentation**: Check docs first
4. **Code Examples**: Look at example applications

### How to Ask for Help

1. **Search First**: Check if someone already asked
2. **Be Specific**: Provide minimal reproduction case
3. **Include Context**: OS, Python version, PyElectron version
4. **Be Patient**: Maintainers are volunteers

## 🎉 Recognition

We appreciate all contributions! Contributors will be:
- Listed in the CONTRIBUTORS.md file
- Mentioned in release notes for significant contributions
- Invited to the contributors' Discord channel (when available)

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to PyElectron! Together, we're building the best desktop framework for Python developers. 🐍⚡