# OMOMatrix - Modern Matrix Client

A modern, feature-rich Matrix client built with GTK4 and Python, inspired by Element and Cinny.

## Features

- 🔐 **End-to-End Encryption (E2EE)** - Secure messaging with matrix-nio
- 💾 **Persistent Sessions** - Login once, stay logged in
- 👤 **Profile Pictures** - Avatar support with caching
- 💬 **Room & Space Management** - Join, leave, and navigate rooms/spaces
- 👥 **Collapsible Member List** - View room members on demand
- 🎨 **Modern UI** - Clean, intuitive interface inspired by Element and Cinny
- 🌙 **Dark Theme Support** - Easy on the eyes

## Requirements

- Python 3.10 or higher
- GTK4
- GLib/GObject Introspection

### Linux (Debian/Ubuntu)
```bash
sudo apt install python3 python3-pip python3-venv \
  gir1.2-gtk-4.0 libgirepository1.0-dev gcc \
  libcairo2-dev pkg-config python3-dev
```

### Linux (Fedora)
```bash
sudo dnf install python3 python3-pip \
  gtk4 gobject-introspection-devel gcc \
  cairo-gobject-devel pkg-config python3-devel
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd omomatrix
```

2. Install dependencies:
```bash
pip3 install --user -r requirements.txt
```

## Usage

Run the application:
```bash
python3 main.py
```

On first launch, you'll be prompted to log in with your Matrix credentials:
- Homeserver URL (e.g., https://matrix.org)
- Username
- Password

Your session will be saved securely for future launches.

## Development

This project uses:
- **GTK4** for the user interface
- **matrix-nio** for Matrix protocol implementation
- **SQLite** for local data storage
- **aiohttp** for async HTTP operations

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.
