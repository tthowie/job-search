"""Kept-jobs list screen.

Scrollable list of jobs the user kept during review. Filters: All / Applied
only / Not-applied only.

Keys:
    ↑/↓     scroll
    Space   toggle applied
    O       open posting in default browser
    A       filter: all
    Y       filter: applied
    N       filter: not applied
    Q       quit
"""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static, Header, Footer

from .. import storage
from ..storage import Job


LIST_CSS = """
Screen {
    background: #0e1726;
    color: #e6eef9;
}

#filter-line {
    padding: 0 2;
    color: #9bb1cc;
}

DataTable {
    background: #14223a;
    margin: 1 2;
    border: round #2db5b1;
    height: 1fr;
}

#empty {
    content-align: center middle;
    color: #9bb1cc;
    height: 1fr;
}

#status {
    padding: 0 2;
    color: #9bb1cc;
}
"""


FILTERS = ["all", "applied", "not_applied"]


class ListApp(App):
    CSS = LIST_CSS
    TITLE = "Kept Jobs"
    SUB_TITLE = "Space=Applied  O=Open  A=All  Y=Applied  N=Not-applied  Q=Quit"

    BINDINGS = [
        Binding("space", "toggle_applied", "Applied?", priority=True),
        Binding("o", "open_link", "Open", priority=True),
        Binding("a", "filter_all", "All", priority=True),
        Binding("y", "filter_applied", "Applied", priority=True),
        Binding("n", "filter_not_applied", "Pending", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, initial_filter: str = "all"):
        super().__init__()
        self.filter = initial_filter if initial_filter in FILTERS else "all"
        self.jobs: list[Job] = []
        self.row_to_url: dict[int, str] = {}

    # ---- compose -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("", id="filter-line")
        with Vertical():
            yield DataTable(id="jobs", zebra_stripes=True, cursor_type="row")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#jobs", DataTable)
        table.add_columns("Status", "Title", "Company", "Location", "Deadline")
        self._reload()

    # ---- helpers -----------------------------------------------------------

    def _filter_label(self) -> str:
        return {
            "all": "Showing: ALL",
            "applied": "Showing: APPLIED only",
            "not_applied": "Showing: NOT applied only",
        }[self.filter]

    def _filtered(self) -> list[Job]:
        all_jobs = storage.list_kept()
        if self.filter == "applied":
            return [j for j in all_jobs if j.applied]
        if self.filter == "not_applied":
            return [j for j in all_jobs if not j.applied]
        return all_jobs

    def _reload(self) -> None:
        table = self.query_one("#jobs", DataTable)
        table.clear()
        self.row_to_url.clear()
        self.jobs = self._filtered()
        for i, j in enumerate(self.jobs):
            check = (
                Text("✓ applied", style="bold green")
                if j.applied
                else Text("☐ pending", style="grey50")
            )
            table.add_row(
                check,
                (j.title or "(untitled)")[:80],
                j.company[:24],
                j.location[:32],
                j.deadline[:24],
            )
            self.row_to_url[i] = j.url
        self.query_one("#filter-line", Static).update(self._filter_label())
        n_app = sum(1 for j in storage.list_kept() if j.applied)
        n_total = len(storage.list_kept())
        self.query_one("#status", Static).update(
            f"{n_total} kept · {n_app} applied · {n_total - n_app} pending"
        )

    def _current_url(self) -> str | None:
        table = self.query_one("#jobs", DataTable)
        if not self.jobs:
            return None
        try:
            row = table.cursor_row
        except Exception:
            return None
        return self.row_to_url.get(row)

    # ---- actions -----------------------------------------------------------

    def action_toggle_applied(self) -> None:
        url = self._current_url()
        if not url:
            return
        # Look up current applied state
        current = next((j for j in storage.list_kept() if j.url == url), None)
        if current is None:
            return
        storage.set_applied(url, not current.applied)
        # Preserve cursor position across the reload
        table = self.query_one("#jobs", DataTable)
        row = table.cursor_row
        self._reload()
        try:
            if self.jobs:
                table.move_cursor(row=min(row, len(self.jobs) - 1))
        except Exception:
            pass

    def action_open_link(self) -> None:
        url = self._current_url()
        if url:
            webbrowser.open(url)

    def action_filter_all(self) -> None:
        self.filter = "all"
        self._reload()

    def action_filter_applied(self) -> None:
        self.filter = "applied"
        self._reload()

    def action_filter_not_applied(self) -> None:
        self.filter = "not_applied"
        self._reload()

    def action_quit(self) -> None:
        self.exit()


def run_list(initial_filter: str = "all") -> None:
    ListApp(initial_filter=initial_filter).run()
