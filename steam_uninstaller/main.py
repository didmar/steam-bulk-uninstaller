#!/usr/bin/env python3
"""Steam Bulk Uninstaller - Entry point."""

import argparse
import sys

from .steam import find_steam_root, get_all_installed_games
from .tui import run_tui


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="A TUI for cleanly uninstalling Steam games on Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  steam-bulk-uninstaller          Launch the interactive TUI
  steam-bulk-uninstaller --dry-run  Preview what would be deleted without deleting
  steam-bulk-uninstaller --list   List all installed games and exit
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview mode - don't actually delete anything",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_games",
        help="List all installed games and exit",
    )

    args = parser.parse_args()

    # Check Steam installation
    steam_root = find_steam_root()
    if steam_root is None:
        print("Error: Could not find Steam installation.", file=sys.stderr)
        print(
            "Checked: ~/.local/share/Steam, ~/.steam/steam, ~/.steam/debian-installation",
            file=sys.stderr,
        )
        return 1

    # List mode
    if args.list_games:
        games = get_all_installed_games()
        if not games:
            print("No installed games found.")
            return 0

        print(f"Found {len(games)} installed games:\n")

        # Calculate column widths
        name_width = max(len(g.name) for g in games)
        name_width = min(name_width, 50)  # Cap at 50 chars

        for game in games:
            name = game.name[:50]
            proton = "Proton" if game.has_compatdata else "Native"
            print(f"  {name:<{name_width}}  {game.format_size():>10}  {proton}")

        total_size = sum(g.size_on_disk for g in games)
        print(f"\nTotal: {len(games)} games")
        return 0

    # Run TUI
    try:
        run_tui(dry_run=args.dry_run)
        return 0
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
