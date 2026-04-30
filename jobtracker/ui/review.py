"""Review screen — flip through unreviewed jobs one at a time.

Layout (top to bottom):

    +----------------------------------------------------+
    | Job title                                          |  header
    | Company  ·  Location  ·  Source                    |
    +----------------------------------------------------+
    | Description                                        |  body (scrollable)
    | ...                                                |
    | Required qualifications                            |
    | ...                                                |
    +----------------------------------------------------+
    | Application deadline: ...                          |  footer
    | [K]eep   [D]iscard   [S]kip   [Q]uit               |
    +----------------------------------------------------+
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static, Header, Footer

from .. import storage
from ..storage import Job


REVIEW_CSS = """
Screen {
    background: #0e1726;
    color: #e6eef9;
}

#card {
    margin: 1 2;
    padding: 1 2;
    border: round #2db5b1;
    background: #14223a;
    height: 1fr;
}

#title-line {
    text-style: bold;
    color: #ffd166;
    padding: 0 0 1 0;
}

#meta-line {
    color: #9bb1cc;
    padding: 0 0 1 0;
}

.section-heading {
    text-style: bold underline;
    color: #2db5b1;
    padding: 1 0 0 0;
}

.section-body {
    padding: 0 0 1 0;
}

#deadline {
    text-style: bold;
    color: #ef476f;
    padding: 1 0 0 0;
}

#progress {
    color: #9bb1cc;
    text-align: right;
    padding: 0 0 1 0;
}

#empty {
    content-align: center middle;
    color: #9bb1cc;
    height: 1fr;
}
"""


class ReviewApp(App):
    """Textual app for reviewing unreviewed jobs."""

    CSS = REVIEW_CSS
    TITLE = "Job Review"
    SUB_TITLE = "K=Keep  D=Discard  S=Skip  Q=Quit"

    BINDINGS = [
        Binding("k", "keep", "Keep", priority=True),
        Binding("d", "discard", "Discard", priority=True),
        Binding("s", "skip", "Skip", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, jobs: list[Job]):
        super().__init__()
        self.jobs = jobs
        self.index = 0

    # ---- compose / mount ---------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        if not self.jobs:
            yield Static(
                "No unreviewed jobs.\n\nRun  python jobs.py fetch  first.",
                id="empty",
            )
        else:
            with VerticalScroll(id="card"):
                yield Static("", id="progress")
                yield Static("", id="title-line")
                yield Static("", id="meta-line")
                yield Static("Description", classes="section-heading")
                yield Static("", id="description", classes="section-body")
                yield Static("Required qualifications", classes="section-heading")
                yield Static("", id="qualifications", classes="section-body")
                yield Static("", id="deadline")
        yield Footer()

    def on_mount(self) -> None:
        self._render()

    # ---- helpers -----------------------------------------------------------

    def _current(self) -> Job | None:
        if 0 <= self.index < len(self.jobs):
            return self.jobs[self.index]
        return None

    def _render(self) -> None:
        job = self._current()
        if job is None:
            return
        self.query_one("#progress", Static).update(
            f"Job {self.index + 1} of {len(self.jobs)}"
        )
        self.query_one("#title-line", Static).update(job.title or "(no title)")
        meta = " · ".join(p for p in [
            job.company or "Unknown company",
            job.location or "Location unknown",
            job.site_id,
        ] if p)
        self.query_one("#meta-line", Static).update(meta)
        self.query_one("#description", Static).update(
            job.description or "[i]No description parsed.[/i]"
        )
        self.query_one("#qualifications", Static).update(
            job.qualifications or "[i]No qualifications parsed.[/i]"
        )
        deadline = job.deadline or "(no deadline parsed)"
        self.query_one("#deadline", Static).update(
            f"Application deadline: {deadline}"
        )

    def _advance(self, kept: bool | None) -> None:
        """Advance to the next job, recording the decision if not skipped."""
        job = self._current()
        if job is not None and kept is not None:
            storage.mark_reviewed(job.url, kept=kept)
            if kept:
                storage.add_kept(job)
        self.index += 1
        if self.index >= len(self.jobs):
            self.exit()
        else:
            self._render()

    # ---- actions -----------------------------------------------------------

    def action_keep(self) -> None:
        self._advance(kept=True)

    def action_discard(self) -> None:
        self._advance(kept=False)

    def action_skip(self) -> None:
        # Move to next without marking reviewed
        self.index += 1
        if self.index >= len(self.jobs):
            self.exit()
        else:
            self._render()

    def action_quit(self) -> None:
        self.exit()


def run_review() -> None:
    jobs = storage.list_unreviewed()
    ReviewApp(jobs).run()
