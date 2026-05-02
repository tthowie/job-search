"""Scrollable site enable/disable screen.

Keys:
    Up/Down  scroll
    Space    toggle enabled
    Q        quit
"""

from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static

from ..config import Config, Site


SITE_CSS = """
Screen {
    background: #0e1726;
    color: #e6eef9;
}

#help-line {
    padding: 0 2;
    color: #9bb1cc;
}

DataTable {
    background: #14223a;
    margin: 1 2;
    border: round #2db5b1;
    height: 1fr;
}

#status {
    padding: 0 2;
    color: #9bb1cc;
}
"""


class SiteToggleApp(App):
    CSS = SITE_CSS
    TITLE = "Configured Sites"
    SUB_TITLE = "Space=Enable/disable  Q=Back"

    BINDINGS = [
        Binding("space", "toggle_enabled", "Enable?", priority=True),
        Binding("q", "quit", "Back", priority=True),
    ]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.sites: list[Site] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("Use Up/Down to move, Space to enable or disable.", id="help-line")
        with Vertical():
            yield DataTable(id="sites", zebra_stripes=True, cursor_type="row")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#sites", DataTable)
        table.add_columns("Enabled", "ID", "Name", "Scraper", "URL")
        self._reload()

    def _reload(self) -> None:
        table = self.query_one("#sites", DataTable)
        table.clear()
        self.sites = self.cfg.sites
        for site in self.sites:
            state = (
                Text("enabled", style="bold green")
                if site.enabled
                else Text("disabled", style="bold red")
            )
            table.add_row(
                state,
                site.id,
                site.name[:32],
                site.scraper,
                self._display_url(site.url)[:80],
            )
        enabled = sum(1 for site in self.sites if site.enabled)
        total = len(self.sites)
        self.query_one("#status", Static).update(
            f"{total} sites | {enabled} enabled | {total - enabled} disabled"
        )

    def _current_site(self) -> Site | None:
        table = self.query_one("#sites", DataTable)
        if not self.sites:
            return None
        row = table.cursor_row
        if 0 <= row < len(self.sites):
            return self.sites[row]
        return None

    @staticmethod
    def _display_url(url: str) -> str:
        return url.replace("{keyword}", "<global keywords>")

    def action_toggle_enabled(self) -> None:
        site = self._current_site()
        if site is None:
            return
        table = self.query_one("#sites", DataTable)
        row = table.cursor_row
        site.enabled = not site.enabled
        self.cfg.save()
        self._reload()
        table.move_cursor(row=row)

    def action_quit(self) -> None:
        self.exit()


def run_site_toggle(cfg: Config) -> None:
    SiteToggleApp(cfg).run()
