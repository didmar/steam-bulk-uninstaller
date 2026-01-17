# Steam Bulk Uninstaller

A TUI app to uninstall many Steam games at once on Linux, as a work around Steam's buggy right-click context menu.

[![asciicast](https://asciinema.org/a/gyGmvlFObUsRkVQg.svg)](https://asciinema.org/a/gyGmvlFObUsRkVQg)

## Why?

Steam on Linux has a known issue where the right-click context menu often fails to open (roughly 1 in 10 clicks works). This makes uninstalling games frustrating. This tool provides a reliable alternative that:

- Lists all installed games across all Steam library folders
- Allows batch selection and uninstallation
- Performs clean uninstalls that Steam recognizes (no "corrupted" warnings)

## Installation

```bash
cd ~/steam-bulk-uninstaller
pip install -e .
```

Or run directly without installing:

```bash
cd ~/steam-bulk-uninstaller
python -m steam_uninstaller.main
```

## Usage

```bash
# Launch the interactive TUI
steam-bulk-uninstaller

# Preview mode - shows what would be deleted without deleting
steam-bulk-uninstaller --dry-run

# List all installed games and exit
steam-bulk-uninstaller --list
```

## TUI Controls

| Key | Action |
|-----|--------|
| Space | Toggle game selection |
| Enter | Confirm selection |
| A | Select all visible games |
| N | Deselect all |
| Escape | Clear filter |
| Q | Quit |

You can also type in the filter box to search for games by name.

## What Gets Deleted

For each game, the uninstaller removes:

1. **Manifest file** - `steamapps/appmanifest_<appid>.acf`
2. **Game files** - `steamapps/common/<game_folder>/`
3. **Proton data** - `steamapps/compatdata/<appid>/` (Windows games via Proton)
4. **Shader cache** - `steamapps/shadercache/<appid>/`

This is the same cleanup Steam performs internally, so games will appear as "not installed" rather than corrupted.

## Features

- Auto-detects all Steam library folders (parses `libraryfolders.vdf`)
- Shows game sizes and whether they use Proton
- Confirmation screen with total space to be freed
- Progress tracking during uninstallation
- Warns if Steam is currently running
- Dry-run mode for safe preview

## Requirements

- Python 3.10+
- Linux with Steam installed
- textual (installed automatically)

## License

MIT
