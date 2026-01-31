# OMOMatrix

A lightweight, high-performance Matrix client built with **Python**, **Qt5 (PyQt5)**, and **matrix-nio**. Designed to be fast and memory-efficient while maintaining a modern, Discord-like 3-column layout.

## Features

- **Blazing Fast Performance**:
    - Optimized room switching with conditional history backfilling.
    - Asynchronous core powered by `asyncio` and `matrix-nio`.
- **Modern UI/UX**:
    - **3-column layout** (Spaces, Rooms, Chat).
    - **Colorful Usernames**: Unique, consistent colors for every user.
    - **Beautiful Replies**: Styled HTML-based reply blocks with name resolution.
    - **Interactive Quotes**: Truncated long quotes with "Click to expand" functionality.
    - **Jump-to-Message**: Double-click a reply to automatically scroll to the original message.
    - **High-Res Images**: Integrated image viewer with support for full-resolution rendering.
- **Matrix Features**:
    - **Spaces Support**: Navigate easily between Matrix Spaces.
    - **Space-less Rooms**: Dedicated section for rooms not belonging to any space.
    - **Join by Alias/ID**: Easily join new rooms via the sidebar.
    - **Member Display Names**: Automatically resolves long MXIDs to friendly display names.
    - **Message History**: Seamless backfilling of previous room messages.
- **Robust Reliability**: Proper handling of multi-line messages and dynamic row heights.

## Getting Started

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/JustOMORI7/omomatrix.git
   cd omomatrix
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python main.pyw
   ```

## Configuration

The application will prompt for your homeserver URL, username, and password upon first launch. Credentials are used to establish a session via `matrix-nio`.

## Project Structure

- `core/`: Matrix client logic and worker threads.
- `gui/`: Widgets, windows, and custom delegates.
- `models/`: Qt models for rooms, spaces, and messages.
- `utils/`: Image caching and Qt helpers.

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
