"""Textual TUI for Steam game uninstaller."""

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

from .steam import SteamGame, get_all_installed_games, is_steam_running
from .uninstaller import (
    UninstallSummary,
    calculate_total_size,
    uninstall_games,
)


def format_size(size: int) -> str:
    """Return human-readable size string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class GameListScreen(Screen):
    """Main screen showing list of installed games."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_selection", "Toggle", show=True),
        Binding("a", "select_all", "Select All"),
        Binding("n", "select_none", "Select None"),
        Binding("escape", "clear_filter", "Clear Filter"),
    ]

    def __init__(self, games: list[SteamGame], dry_run: bool = False):
        super().__init__()
        self.games = games
        self.dry_run = dry_run
        self.selected: set[str] = set()  # Set of appids
        self.filtered_games: list[SteamGame] = games.copy()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(
                f"Found [bold]{len(self.games)}[/bold] installed games. "
                "Select games to uninstall.",
                id="subtitle",
            ),
            Input(placeholder="Filter games...", id="filter-input"),
            DataTable(id="games-table"),
            Static("", id="selection-info"),
            Horizontal(
                Button(
                    "Proceed to Uninstall",
                    id="proceed-btn",
                    variant="warning",
                ),
                id="action-row",
            ),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the data table."""
        table = self.query_one("#games-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        table.add_column("", key="selected", width=3)
        table.add_column("Game", key="name")
        table.add_column("Size", key="size", width=12)
        table.add_column("Played", key="playtime", width=10)
        table.add_column("Proton", key="proton", width=8)
        table.add_column("Library", key="library", width=30)

        self._populate_table()

    def _populate_table(self) -> None:
        """Populate or refresh the table with games."""
        table = self.query_one("#games-table", DataTable)
        table.clear()

        for game in self.filtered_games:
            selected = "[bold green]X[/]" if game.appid in self.selected else " "
            proton = "Yes" if game.has_compatdata else "No"

            # Shorten library path for display
            lib_str = str(game.library_path)
            if lib_str.startswith(str(game.library_path.home())):
                lib_str = "~" + lib_str[len(str(game.library_path.home())) :]

            table.add_row(
                selected,
                game.name,
                game.format_size(),
                game.format_playtime(),
                proton,
                lib_str,
                key=game.appid,
            )

        self._update_selection_info()

    def _update_selection_info(self) -> None:
        """Update the selection summary text."""
        info = self.query_one("#selection-info", Static)
        if not self.selected:
            info.update("")
            return

        selected_games = [g for g in self.games if g.appid in self.selected]
        total_size = calculate_total_size(selected_games)
        mode = "[bold yellow](DRY RUN)[/] " if self.dry_run else ""

        info.update(
            f"{mode}[bold]{len(self.selected)}[/] games selected, "
            f"[bold]{format_size(total_size)}[/] will be freed"
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter games based on search input."""
        filter_text = event.value.lower()
        if filter_text:
            self.filtered_games = [
                g for g in self.games if filter_text in g.name.lower()
            ]
        else:
            self.filtered_games = self.games.copy()
        self._populate_table()

    def action_toggle_selection(self) -> None:
        """Toggle selection of current row."""
        table = self.query_one("#games-table", DataTable)
        if table.cursor_row is None:
            return

        # Save cursor position before repopulating
        saved_row = table.cursor_row

        # Get the appid from the row key using coordinate_to_cell_key
        try:
            cell_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            appid = str(cell_key.row_key.value)
        except Exception:
            return

        if appid in self.selected:
            self.selected.discard(appid)
        else:
            self.selected.add(appid)

        self._populate_table()

        # Restore cursor position
        try:
            table.move_cursor(row=saved_row)
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key or click)."""
        if event.row_key:
            appid = str(event.row_key.value)
            if appid in self.selected:
                self.selected.discard(appid)
            else:
                self.selected.add(appid)
            self._populate_table()

    def action_select_all(self) -> None:
        """Select all visible games."""
        for game in self.filtered_games:
            self.selected.add(game.appid)
        self._populate_table()

    def action_select_none(self) -> None:
        """Deselect all games."""
        self.selected.clear()
        self._populate_table()

    def action_clear_filter(self) -> None:
        """Clear the filter input."""
        self.query_one("#filter-input", Input).value = ""

    def action_confirm(self) -> None:
        """Proceed to confirmation screen."""
        if not self.selected:
            self.notify("No games selected!", severity="warning")
            return

        selected_games = [g for g in self.games if g.appid in self.selected]
        self.app.push_screen(
            ConfirmScreen(selected_games, dry_run=self.dry_run)
        )

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "proceed-btn":
            self.action_confirm()


class ConfirmScreen(Screen):
    """Confirmation screen before uninstalling."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "proceed", "Yes, Uninstall"),
    ]

    def __init__(self, games: list[SteamGame], dry_run: bool = False):
        super().__init__()
        self.games = games
        self.dry_run = dry_run
        self.total_size = calculate_total_size(games)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(
                "[bold red]Confirm Uninstallation[/]" if not self.dry_run
                else "[bold yellow]Confirm Uninstallation (DRY RUN)[/]",
                id="confirm-title",
            ),
            Static(
                f"You are about to uninstall [bold]{len(self.games)}[/] games, "
                f"freeing approximately [bold]{format_size(self.total_size)}[/].",
                id="confirm-summary",
            ),
            Static("[bold]Games to remove:[/]", id="games-header"),
            Vertical(
                *[
                    Static(f"  - {g.name} ({g.format_size()})")
                    for g in self.games[:20]
                ],
                Static(f"  ... and {len(self.games) - 20} more")
                if len(self.games) > 20
                else Static(""),
                id="games-list",
            ),
            Horizontal(
                Button("Cancel", id="cancel-btn", variant="default"),
                Button(
                    "Uninstall" if not self.dry_run else "Dry Run",
                    id="proceed-btn",
                    variant="error" if not self.dry_run else "warning",
                ),
                id="button-row",
            ),
            id="confirm-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "proceed-btn":
            self.action_proceed()

    def action_cancel(self) -> None:
        """Go back to game list."""
        self.app.pop_screen()

    def action_proceed(self) -> None:
        """Start the uninstallation process."""
        self.app.push_screen(ProgressScreen(self.games, dry_run=self.dry_run))


class ProgressScreen(Screen):
    """Screen showing uninstallation progress."""

    def __init__(self, games: list[SteamGame], dry_run: bool = False):
        super().__init__()
        self.games = games
        self.dry_run = dry_run
        self.summary: UninstallSummary | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(
                "[bold]Uninstalling games...[/]" if not self.dry_run
                else "[bold yellow]Dry run - no files will be deleted[/]",
                id="progress-title",
            ),
            ProgressBar(id="progress-bar", total=len(self.games)),
            Static("", id="current-game"),
            RichLog(id="progress-log", highlight=True, markup=True),
            id="progress-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Start the uninstallation process."""
        self.run_uninstall()

    @work(thread=True)
    def run_uninstall(self) -> None:
        """Run the uninstallation in a background thread."""
        log = self.query_one("#progress-log", RichLog)
        progress = self.query_one("#progress-bar", ProgressBar)
        current = self.query_one("#current-game", Static)

        def progress_callback(index: int, total: int, game: SteamGame) -> None:
            self.app.call_from_thread(progress.update, progress=index)
            self.app.call_from_thread(
                current.update,
                f"[bold]Processing:[/] {game.name}",
            )

        self.summary = uninstall_games(
            self.games,
            dry_run=self.dry_run,
            progress_callback=progress_callback,
        )

        # Update progress to complete
        self.app.call_from_thread(progress.update, progress=len(self.games))

        # Log results
        for result in self.summary.results:
            if result.success:
                self.app.call_from_thread(
                    log.write,
                    f"[green]OK[/] {result.game.name} "
                    f"({format_size(result.bytes_freed)})",
                )
            else:
                self.app.call_from_thread(
                    log.write,
                    f"[red]FAILED[/] {result.game.name}: {result.error}",
                )

        # Show completion
        self.app.call_from_thread(self.show_completion)

    def show_completion(self) -> None:
        """Show completion screen."""
        if self.summary:
            self.app.push_screen(CompletionScreen(self.summary, dry_run=self.dry_run))


class CompletionScreen(Screen):
    """Screen showing final results."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("enter", "quit", "Done"),
    ]

    def __init__(self, summary: UninstallSummary, dry_run: bool = False):
        super().__init__()
        self.summary = summary
        self.dry_run = dry_run

    def compose(self) -> ComposeResult:
        yield Header()

        if self.summary.all_successful:
            title = (
                "[bold green]Uninstallation Complete![/]"
                if not self.dry_run
                else "[bold yellow]Dry Run Complete![/]"
            )
        else:
            title = "[bold yellow]Uninstallation Completed with Errors[/]"

        yield Container(
            Static(title, id="completion-title"),
            Static(
                f"[bold]Games processed:[/] {self.summary.total_games}\n"
                f"[bold]Successful:[/] [green]{self.summary.successful}[/]\n"
                f"[bold]Failed:[/] [red]{self.summary.failed}[/]\n"
                f"[bold]Space freed:[/] {self.summary.format_bytes_freed()}"
                + (" (would be freed)" if self.dry_run else ""),
                id="completion-stats",
            ),
            Button("Done", id="done-btn", variant="primary"),
            id="completion-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle done button."""
        self.app.exit()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()


class SteamUninstallerApp(App):
    """Main application."""

    CSS = """
    #main-container {
        padding: 1 2;
    }

    #subtitle {
        margin-bottom: 1;
    }

    #filter-input {
        margin-bottom: 1;
    }

    #games-table {
        height: 1fr;
        margin-bottom: 1;
    }

    #selection-info {
        height: 1;
        text-align: center;
    }

    #action-row {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    #confirm-container {
        padding: 2 4;
    }

    #confirm-title {
        text-align: center;
        margin-bottom: 2;
    }

    #confirm-summary {
        margin-bottom: 1;
    }

    #games-header {
        margin-top: 1;
    }

    #games-list {
        margin-bottom: 2;
        max-height: 15;
        overflow-y: auto;
    }

    #button-row {
        align: center middle;
        height: 3;
    }

    #button-row Button {
        margin: 0 2;
    }

    #progress-container {
        padding: 2 4;
    }

    #progress-title {
        margin-bottom: 2;
    }

    #progress-bar {
        margin-bottom: 1;
    }

    #current-game {
        margin-bottom: 1;
    }

    #progress-log {
        height: 1fr;
        border: solid green;
    }

    #completion-container {
        padding: 2 4;
        align: center middle;
    }

    #completion-title {
        text-align: center;
        margin-bottom: 2;
    }

    #completion-stats {
        margin-bottom: 2;
    }

    #done-btn {
        margin-top: 2;
    }
    """

    TITLE = "Steam Game Uninstaller"

    def __init__(self, dry_run: bool = False):
        super().__init__()
        self.dry_run = dry_run

    def on_mount(self) -> None:
        """Initialize the application."""
        # Check if Steam is running
        if is_steam_running() and not self.dry_run:
            self.notify(
                "Steam is running. Consider closing it first for cleaner uninstall.",
                severity="warning",
                timeout=5,
            )

        # Load games
        games = get_all_installed_games()

        if not games:
            self.notify("No Steam games found!", severity="error")
            self.exit()
            return

        self.push_screen(GameListScreen(games, dry_run=self.dry_run))


def run_tui(dry_run: bool = False) -> None:
    """Run the TUI application."""
    app = SteamUninstallerApp(dry_run=dry_run)
    app.run()
