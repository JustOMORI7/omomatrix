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
# or
./run.sh
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

### Project Structure

```
omomatrix/
├── main.py              # Application entry point
├── config.py            # Configuration management
├── matrix/              # Matrix client layer
│   ├── client.py        # Matrix client wrapper
│   ├── storage.py       # Credential storage
│   ├── room_manager.py  # Room/space management
│   └── avatar_manager.py # Avatar handling
├── gui/                 # GTK4 UI components
│   ├── application.py   # GTK Application
│   ├── main_window.py   # Main window
│   ├── login_window.py  # Login screen
│   ├── room_list.py     # Room sidebar
│   ├── message_view.py  # Message timeline
│   ├── member_list.py   # Member list
│   ├── widgets/         # Custom widgets
│   └── style.css        # UI styling
└── requirements.txt     # Python dependencies
```

## License

[Your license here]

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.
