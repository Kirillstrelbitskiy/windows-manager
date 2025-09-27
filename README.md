# macOS Window Manager

A lightweight keyboard-driven window manager for macOS that lets you navigate between application windows using keyboard shortcuts.

## Features

- Navigate between windows using keyboard shortcuts (Ctrl+Option+Arrow keys)
- Intelligently selects the next window in the specified direction
- Focuses and raises the selected window

## Requirements

- macOS
- Python 3
- Required Python packages:
  - pyobjc-framework-AppKit
  - pyobjc-framework-Quartz
  - pyobjc-framework-ApplicationServices

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/Kirillstrelbitskiy/windows-manager.git
   cd windows-manager
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Usage

### Starting the window manager:

```bash
./windows_manager.sh
```

### Keyboard shortcuts:

- **Ctrl+Option+Left Arrow**: Focus window to the left
- **Ctrl+Option+Right Arrow**: Focus window to the right
- **Ctrl+Option+Up Arrow**: Focus window above
- **Ctrl+Option+Down Arrow**: Focus window below

## Permissions

This application requires Accessibility permissions to control window focus. When you first run the application, macOS will prompt you to grant these permissions.

To manually enable permissions:
1. Go to System Preferences > Security & Privacy > Privacy > Accessibility
2. Add Terminal or the application you use to run the script

## License

See the [LICENSE](LICENSE) file for details.