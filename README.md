# PyElectron

[![Tests](https://github.com/pyelectron/pyelectron/workflows/Tests/badge.svg)](https://github.com/pyelectron/pyelectron/actions)
[![PyPI version](https://badge.fury.io/py/pyelectron.svg)](https://badge.fury.io/py/pyelectron)
[![Python versions](https://img.shields.io/pypi/pyversions/pyelectron.svg)](https://pypi.org/project/pyelectron/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A pragmatic Python desktop application framework that enables developers to build cross-platform desktop applications using Python as the backend and modern web technologies for the frontend.

## 🎯 Design Philosophy

PyElectron is designed to be **the obvious choice for Python developers** who need desktop apps with modern UI. Instead of competing on impossible metrics, we focus on:

- **Python-Native**: Seamless integration with NumPy, Pandas, scikit-learn, and the entire Python ecosystem
- **Simplicity First**: JSON-RPC over native IPC, no complex certificates or protocols
- **Security by Default**: Process isolation, input validation, and secure defaults
- **Realistic Performance**: 100-150MB apps that work reliably vs 30MB apps that break

## 🚀 Quick Start

### Installation

```bash
# Install PyElectron
pip install pyelectron

# Install platform-specific WebView dependencies
# Windows (WebView2 - usually pre-installed)
pip install "pyelectron[windows]"

# macOS (WKWebView)
pip install "pyelectron[macos]"

# Linux (WebKit2GTK)
pip install "pyelectron[linux]"
```

### Create Your First App

```bash
# Create a new project
pyelectron create my-app

# Start development server
cd my-app
pyelectron dev
```

### Basic Usage

```python
import pyelectron

# Create app
app = pyelectron.create_app("My Data App")

# Expose Python function to frontend
@app.api.expose('process_data')
async def process_data(data):
    import pandas as pd
    df = pd.DataFrame(data)
    return df.describe().to_dict()

# Run the application
app.run()
```

```javascript
// Frontend (JavaScript)
const result = await pyelectron.invoke('process_data', {
    values: [1, 2, 3, 4, 5]
});
console.log(result);
```

## ✨ Key Features

### 🔐 **Security-First Architecture**
- **Process isolation**: Main, renderer, and worker processes
- **Secure IPC**: JSON-RPC over Unix sockets/named pipes
- **Input validation**: Automatic sanitization and validation
- **Permission system**: Simple but effective access control

### 🚀 **Modern Development Experience**
- **Hot reload**: Process-restart with state preservation
- **Integrated debugging**: VS Code, PyCharm, and Chrome DevTools
- **Performance profiling**: Built-in Python and IPC profiling
- **CLI tools**: Project scaffolding and build automation

### 📊 **Data Science Ready**
- **Shared memory**: Zero-copy NumPy array sharing
- **Binary protocols**: Efficient large data transfer
- **ML integration**: Seamless scikit-learn, PyTorch integration
- **Visualization**: Easy matplotlib, plotly integration

### 🔧 **Cross-Platform**
- **Native WebView**: WebView2 (Windows), WKWebView (macOS), WebKit2GTK (Linux)
- **Consistent API**: Same code across all platforms
- **Platform optimization**: Leverage OS-specific features

## 📊 Performance Targets

| Metric | PyElectron Target | Electron Typical | Tauri Typical |
|--------|------------------|------------------|---------------|
| Memory Usage | 100-150MB | ~150MB | ~40MB |
| Binary Size | 100-200MB | ~80MB | ~3MB |
| Startup Time | 2-3s | ~3-5s | <1s |
| IPC Latency | 1-2ms | ~2-5ms | <1ms |

*PyElectron targets realistic performance for Python apps rather than impossible metrics.*

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     PyElectron Application                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │  Main Process  │◄──►│    Renderer     │◄──►│   Workers    │ │
│  │    (Python)    │    │   (WebView)     │    │   (Python)   │ │
│  │                │    │                 │    │              │ │
│  │  - Lifecycle   │    │  - UI Rendering │    │  - ML Tasks  │ │
│  │  - IPC Router  │    │  - User Input   │    │  - Data Proc │ │
│  │  - Security    │    │  - Sandboxed    │    │  - Background │ │
│  └────────────────┘    └─────────────────┘    └──────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                      Secure IPC Layer                           │
│  JSON-RPC over Unix Sockets/Named Pipes + Shared Memory         │
└──────────────────────────────────────────────────────────────────┘
```

## 🛠️ Development

### Prerequisites

- Python 3.8 or higher
- Platform-specific WebView dependencies (see installation)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/pyelectron/pyelectron.git
cd pyelectron

# Set up development environment
make dev-setup

# Run tests
make test

# Run linting
make lint

# Format code
make format

# Build documentation
make docs
```

### Running Tests

```bash
# All tests
make test

# Fast tests only (no integration/slow tests)
make test-fast

# Integration tests
make test-integration

# Performance benchmarks
make benchmark
```

## 📚 Documentation

- **[Getting Started Guide](https://pyelectron.readthedocs.io/getting-started/)**
- **[API Reference](https://pyelectron.readthedocs.io/api/)**
- **[Examples](https://github.com/pyelectron/examples)**
- **[Architecture Guide](https://pyelectron.readthedocs.io/architecture/)**

## 🎯 Use Cases

### Perfect For:
- **Data Science Apps**: Dashboards, ML model UIs, data visualization
- **Python-Heavy Tools**: Developer tools, automation GUIs, config managers
- **Enterprise Apps**: Internal tools that leverage existing Python infrastructure
- **Prototyping**: Rapid development of desktop app concepts

### Consider Alternatives For:
- **Performance-Critical**: Games, real-time media processing (use Tauri)
- **Tiny Distributions**: Apps that must be <50MB (use Tauri)
- **Web Development Teams**: Teams with primarily JS expertise (use Electron)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`make test`)
5. Run linting (`make lint`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by [Electron](https://electronjs.org/) and [Tauri](https://tauri.app/)
- Built on the excellent Python ecosystem
- Special thanks to the WebView and IPC library maintainers

## 📊 Project Status

PyElectron is currently in **alpha development**. We're working toward a stable v1.0 release with the following roadmap:

- **Phase 1** (Current): Core foundation with basic IPC and WebView
- **Phase 2**: Features and capabilities (shared memory, file system)
- **Phase 3**: Developer experience (hot reload, debugging)
- **Phase 4**: Production readiness (packaging, auto-updates)

Star the repo to follow our progress! ⭐