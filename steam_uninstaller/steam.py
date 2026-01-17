"""Steam library detection and game parsing."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SteamGame:
    """Represents an installed Steam game."""

    appid: str
    name: str
    install_dir: str
    size_on_disk: int
    library_path: Path
    has_compatdata: bool
    has_shadercache: bool
    playtime_minutes: int = 0

    @property
    def manifest_path(self) -> Path:
        """Path to the appmanifest file."""
        return self.library_path / "steamapps" / f"appmanifest_{self.appid}.acf"

    @property
    def game_path(self) -> Path:
        """Path to the game installation folder."""
        return self.library_path / "steamapps" / "common" / self.install_dir

    @property
    def compatdata_path(self) -> Path:
        """Path to Proton compatibility data."""
        return self.library_path / "steamapps" / "compatdata" / self.appid

    @property
    def shadercache_path(self) -> Path:
        """Path to shader cache."""
        return self.library_path / "steamapps" / "shadercache" / self.appid

    def format_size(self) -> str:
        """Return human-readable size string."""
        size = self.size_on_disk
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def format_playtime(self) -> str:
        """Return human-readable playtime string."""
        if self.playtime_minutes == 0:
            return "-"
        hours = self.playtime_minutes / 60
        return f"{hours:.1f}h"


def parse_vdf(content: str) -> dict:
    """
    Parse Valve's VDF format into a Python dictionary.

    VDF format:
        "key"  "value"
        "section"
        {
            "nested_key"  "nested_value"
        }
    """
    result = {}
    stack = [result]
    current_key = None

    # Pattern to match quoted strings
    token_pattern = re.compile(r'"([^"]*)"|\{|\}')

    tokens = token_pattern.findall(content)
    i = 0

    # Re-scan with positions to handle braces
    for match in token_pattern.finditer(content):
        token = match.group()

        if token == "{":
            # Start new nested dict
            if current_key is not None:
                new_dict = {}
                stack[-1][current_key] = new_dict
                stack.append(new_dict)
                current_key = None
        elif token == "}":
            # End current dict
            if len(stack) > 1:
                stack.pop()
        else:
            # Quoted string - extract value
            value = match.group(1)
            if current_key is None:
                current_key = value
            else:
                stack[-1][current_key] = value
                current_key = None

    return result


def find_steam_root() -> Path | None:
    """
    Find the Steam installation directory.

    Checks common locations on Linux.
    """
    candidates = [
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / ".steam" / "steam",
        Path.home() / ".steam" / "debian-installation",
    ]

    for path in candidates:
        if path.exists() and (path / "steamapps").exists():
            return path

    return None


def get_library_folders(steam_root: Path) -> list[Path]:
    """
    Get all Steam library folders by parsing libraryfolders.vdf.

    Returns a list of library paths including the main Steam folder.
    """
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"

    if not vdf_path.exists():
        return [steam_root]

    content = vdf_path.read_text()
    data = parse_vdf(content)

    libraries = []

    # The structure is: {"libraryfolders": {"0": {"path": "..."}, "1": {...}}}
    library_data = data.get("libraryfolders", {})

    for key, value in library_data.items():
        if isinstance(value, dict) and "path" in value:
            lib_path = Path(value["path"])
            if lib_path.exists():
                libraries.append(lib_path)

    # Ensure steam_root is included
    if steam_root not in libraries:
        libraries.insert(0, steam_root)

    return libraries


def get_playtime_data(steam_root: Path) -> dict[str, int]:
    """
    Get playtime data from localconfig.vdf.

    Returns a dict mapping appid -> playtime in minutes.
    """
    userdata_path = steam_root / "userdata"
    if not userdata_path.exists():
        return {}

    # Find user directories (there may be multiple Steam accounts)
    playtime: dict[str, int] = {}

    for user_dir in userdata_path.iterdir():
        if not user_dir.is_dir():
            continue

        config_file = user_dir / "config" / "localconfig.vdf"
        if not config_file.exists():
            continue

        try:
            content = config_file.read_text()
            data = parse_vdf(content)

            # Navigate to Software/Valve/Steam/apps
            apps = (
                data.get("UserLocalConfigStore", {})
                .get("Software", {})
                .get("Valve", {})
                .get("Steam", {})
                .get("apps", {})
            )

            for appid, app_data in apps.items():
                if isinstance(app_data, dict) and "Playtime" in app_data:
                    try:
                        minutes = int(app_data["Playtime"])
                        # Keep the highest playtime if multiple users
                        if appid not in playtime or minutes > playtime[appid]:
                            playtime[appid] = minutes
                    except ValueError:
                        pass

        except Exception:
            continue

    return playtime


def get_installed_games(library_path: Path, playtime_data: dict[str, int] | None = None) -> list[SteamGame]:
    """
    Get all installed games from a Steam library folder.

    Parses appmanifest_*.acf files in the steamapps directory.
    """
    steamapps = library_path / "steamapps"
    if not steamapps.exists():
        return []

    games = []

    for manifest in steamapps.glob("appmanifest_*.acf"):
        try:
            content = manifest.read_text()
            data = parse_vdf(content)

            app_state = data.get("AppState", {})
            if not app_state:
                continue

            appid = app_state.get("appid", "")
            name = app_state.get("name", "Unknown")
            install_dir = app_state.get("installdir", "")
            size_str = app_state.get("SizeOnDisk", "0")

            # Skip runtime/tool entries (like Proton, Steam Linux Runtime)
            if "Runtime" in name or "Proton" in name:
                continue

            try:
                size_on_disk = int(size_str)
            except ValueError:
                size_on_disk = 0

            # Check if compatdata and shadercache exist
            compatdata_path = steamapps / "compatdata" / appid
            shadercache_path = steamapps / "shadercache" / appid

            game = SteamGame(
                appid=appid,
                name=name,
                install_dir=install_dir,
                size_on_disk=size_on_disk,
                library_path=library_path,
                has_compatdata=compatdata_path.exists(),
                has_shadercache=shadercache_path.exists(),
                playtime_minutes=playtime_data.get(appid, 0) if playtime_data else 0,
            )

            # Only include if game folder exists
            if game.game_path.exists():
                games.append(game)

        except Exception:
            # Skip malformed manifests
            continue

    return sorted(games, key=lambda g: g.name.lower())


def get_all_installed_games() -> list[SteamGame]:
    """Get all installed games across all Steam libraries."""
    steam_root = find_steam_root()
    if steam_root is None:
        return []

    libraries = get_library_folders(steam_root)
    playtime_data = get_playtime_data(steam_root)
    all_games = []

    for library in libraries:
        all_games.extend(get_installed_games(library, playtime_data))

    return sorted(all_games, key=lambda g: g.name.lower())


def is_steam_running() -> bool:
    """Check if Steam is currently running."""
    import psutil

    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name and name.lower() in ("steam", "steam.exe"):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False
