"""Game uninstallation logic."""

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .steam import SteamGame

logger = logging.getLogger(__name__)


@dataclass
class UninstallResult:
    """Result of uninstalling a single game."""

    game: SteamGame
    success: bool
    error: str | None = None
    bytes_freed: int = 0


@dataclass
class UninstallSummary:
    """Summary of batch uninstallation."""

    total_games: int
    successful: int
    failed: int
    total_bytes_freed: int
    results: list[UninstallResult]

    @property
    def all_successful(self) -> bool:
        return self.failed == 0

    def format_bytes_freed(self) -> str:
        """Return human-readable size string."""
        size = self.total_bytes_freed
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


def get_dir_size(path: Path) -> int:
    """Calculate total size of a directory."""
    if not path.exists():
        return 0

    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass

    return total


def get_game_paths(game: SteamGame) -> list[tuple[Path, str]]:
    """
    Get all paths that need to be deleted for a game.

    Returns list of (path, description) tuples.
    """
    paths = []

    # Manifest file (must exist)
    paths.append((game.manifest_path, "manifest"))

    # Game installation folder
    if game.game_path.exists():
        paths.append((game.game_path, "game files"))

    # Proton compatibility data
    if game.has_compatdata and game.compatdata_path.exists():
        paths.append((game.compatdata_path, "Proton data"))

    # Shader cache
    if game.has_shadercache and game.shadercache_path.exists():
        paths.append((game.shadercache_path, "shader cache"))

    return paths


def calculate_total_size(games: list[SteamGame]) -> int:
    """Calculate total size that will be freed by uninstalling games."""
    total = 0
    for game in games:
        # Use reported size from manifest
        total += game.size_on_disk

        # Add compatdata size if exists
        if game.has_compatdata:
            total += get_dir_size(game.compatdata_path)

        # Add shadercache size if exists
        if game.has_shadercache:
            total += get_dir_size(game.shadercache_path)

    return total


def uninstall_game(game: SteamGame, dry_run: bool = False) -> UninstallResult:
    """
    Uninstall a single game.

    Removes:
    - appmanifest_<appid>.acf
    - steamapps/common/<installdir>/
    - steamapps/compatdata/<appid>/ (if exists)
    - steamapps/shadercache/<appid>/ (if exists)

    Args:
        game: The game to uninstall
        dry_run: If True, don't actually delete anything

    Returns:
        UninstallResult with success status and details
    """
    bytes_freed = 0
    paths_to_delete = get_game_paths(game)

    try:
        for path, description in paths_to_delete:
            if not path.exists():
                continue

            # Calculate size before deletion
            if path.is_file():
                size = path.stat().st_size
            else:
                size = get_dir_size(path)

            if not dry_run:
                if path.is_file():
                    path.unlink()
                else:
                    shutil.rmtree(path)

            bytes_freed += size
            logger.info("Deleted %s: %s", description, path)

        return UninstallResult(
            game=game,
            success=True,
            bytes_freed=bytes_freed,
        )

    except PermissionError as e:
        logger.error("Permission denied: %s", e)
        return UninstallResult(
            game=game,
            success=False,
            error=f"Permission denied: {e}",
            bytes_freed=bytes_freed,
        )

    except OSError as e:
        logger.error("OS error: %s", e)
        return UninstallResult(
            game=game,
            success=False,
            error=f"OS error: {e}",
            bytes_freed=bytes_freed,
        )

    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return UninstallResult(
            game=game,
            success=False,
            error=str(e),
            bytes_freed=bytes_freed,
        )


def uninstall_games(
    games: list[SteamGame],
    dry_run: bool = False,
    progress_callback: Callable[[int, int, SteamGame], None] | None = None,
) -> UninstallSummary:
    """
    Uninstall multiple games.

    Args:
        games: List of games to uninstall
        dry_run: If True, don't actually delete anything
        progress_callback: Called with (current_index, total, current_game)

    Returns:
        UninstallSummary with overall results
    """
    results = []
    total = len(games)

    for i, game in enumerate(games):
        if progress_callback:
            progress_callback(i, total, game)

        result = uninstall_game(game, dry_run=dry_run)
        results.append(result)

    successful = sum(1 for r in results if r.success)
    failed = total - successful
    total_bytes = sum(r.bytes_freed for r in results)

    return UninstallSummary(
        total_games=total,
        successful=successful,
        failed=failed,
        total_bytes_freed=total_bytes,
        results=results,
    )
