#!/usr/bin/env python3
"""MSL Job Tracker — main entry point.

Usage::

    python jobs.py             # interactive menu
    python jobs.py fetch       # pull new jobs from all enabled sites
    python jobs.py review      # review unreviewed jobs
    python jobs.py list        # browse kept jobs
    python jobs.py sites       # manage sites
    python jobs.py settings    # change global keywords / location

Add ``--debug`` to any command for verbose logging.
"""

from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.text import Text

from jobtracker import storage
from jobtracker.config import Config, GlobalSettings, Site
from jobtracker.scrapers import get_scraper, REGISTRY
from jobtracker.ui.review import run_review
from jobtracker.ui.list_screen import run_list
from jobtracker.ui.site_screen import run_site_toggle


console = Console()
log = logging.getLogger("jobtracker")


# ---------------------------------------------------------------------------
# Pretty banner / menu
# ---------------------------------------------------------------------------

BANNER = r"""
   __  __ ___ _      _      _    _____           _
  |  \/  / __| |    | |___ | |__|_   _| _ __ _ __| |_____ _ _
  | |\/| \__ \ |__  | / _ \| '_ \ | || '_/ _` / _| / / -_) '_|
  |_|  |_|___/____|_|\___/ |_.__/ |_||_| \__,_\__|_\_\___|_|
"""


def _banner() -> None:
    console.print(Text(BANNER, style="bold cyan"))
    console.print("  [dim]Track Medical Affairs / MSL roles across pharma careers sites[/]\n")


def _menu() -> str:
    table = Table(
        show_header=False, box=None, padding=(0, 1), show_edge=False,
    )
    table.add_column(style="bold yellow", width=3)
    table.add_column(style="white")
    table.add_row("1.", "Fetch new jobs")
    table.add_row("2.", "Review fetched jobs")
    table.add_row("3.", "List kept jobs")
    table.add_row("4.", "Manage sites")
    table.add_row("5.", "Edit global settings (keywords, location)")
    table.add_row("Q.", "Quit")
    console.print(Panel(table, title="[bold]Menu[/]", border_style="cyan"))
    return Prompt.ask("Choose", choices=["1", "2", "3", "4", "5", "q", "Q"], default="1")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_fetch(args: argparse.Namespace) -> None:
    cfg = Config.load()
    target = [s for s in cfg.sites if s.enabled]
    if args.site:
        target = [s for s in target if s.id == args.site]
        if not target:
            console.print(f"[red]No enabled site with id '{args.site}'[/]")
            return

    console.print(f"\n[bold]Fetching from {len(target)} site(s)…[/]\n")
    total_new = 0
    for site in target:
        scraper_cls = get_scraper(site.scraper)
        console.print(f"  · [cyan]{site.name}[/] (scraper: {site.scraper})  …", end="")
        try:
            jobs = scraper_cls(site, cfg.global_settings).fetch()
        except Exception as e:  # noqa: BLE001
            console.print(f" [red]error[/]  ({e})")
            log.exception("scrape failed for %s", site.id)
            continue
        # Skip jobs whose URL is already in fetched.csv
        existing = storage.known_urls()
        new_jobs = [j for j in jobs if j.url not in existing]
        added = storage.append_fetched(new_jobs)
        total_new += added
        console.print(f"  found [bold]{len(jobs)}[/], new [bold green]{added}[/]")

    console.print(f"\n[bold]Done.[/] {total_new} new job(s) added to data/fetched.csv\n")
    if total_new and Confirm.ask("Review the new jobs now?", default=True):
        run_review()


def cmd_review(args: argparse.Namespace) -> None:  # noqa: ARG001
    pending = len(storage.list_unreviewed())
    if pending == 0:
        console.print("[yellow]No unreviewed jobs.[/] Run [bold]python jobs.py fetch[/] first.")
        return
    console.print(f"[bold]{pending}[/] unreviewed job(s). Launching review…")
    run_review()


def cmd_list(args: argparse.Namespace) -> None:
    if args.filter:
        chosen = args.filter
    else:
        console.print("\n[bold]Show which jobs?[/]")
        console.print("  [yellow]A[/] = All     [yellow]Y[/] = Applied only     [yellow]N[/] = Not applied")
        choice = Prompt.ask("Filter", choices=["A", "Y", "N", "a", "y", "n"], default="A").upper()
        chosen = {"A": "all", "Y": "applied", "N": "not_applied"}[choice]
    if not storage.list_kept():
        console.print("[yellow]No kept jobs yet.[/] Review some fetched jobs first.")
        return
    run_list(chosen)


def cmd_sites(args: argparse.Namespace) -> None:  # noqa: ARG001
    cfg = Config.load()
    while True:
        _show_sites(cfg)
        action = Prompt.ask(
            "\n[bold]Site action[/]",
            choices=["a", "e", "r", "t", "b", "A", "E", "R", "T", "B"],
            default="b",
            show_choices=False,
        ).lower()
        # a=add  e=edit  r=remove  t=toggle sites  b=back
        if action == "a":
            _add_site(cfg)
        elif action == "e":
            _edit_site(cfg)
        elif action == "r":
            _remove_site(cfg)
        elif action == "t":
            run_site_toggle(cfg)
        else:
            return
        cfg.save()


def cmd_settings(args: argparse.Namespace) -> None:  # noqa: ARG001
    cfg = Config.load()
    gs = cfg.global_settings
    console.print(Panel.fit(
        f"[bold]Keywords:[/] {', '.join(gs.keywords) or '(none)'}\n"
        f"[bold]Location:[/] {gs.location or '(none)'}\n"
        f"[bold]Max jobs per site:[/] {gs.max_jobs_per_site}",
        title="Current settings",
        border_style="cyan",
    ))
    if Confirm.ask("\nEdit keywords?", default=False):
        _edit_keywords(gs)
    if Confirm.ask("Edit location?", default=False):
        _edit_location(gs)
    if Confirm.ask("Edit max jobs per site?", default=False):
        _edit_max_jobs(gs)
    cfg.save()
    console.print("[green]Saved.[/]")


def _edit_keywords(gs: GlobalSettings) -> None:
    current = ", ".join(gs.keywords) or "(none)"
    console.print(Panel.fit(
        f"[bold]Current keywords:[/] {current}\n\n"
        "[bold]A[/] = Add keywords to the current list\n"
        "[bold]C[/] = Clear the whole keyword list\n"
        "[bold]S[/] = Skip without changing keywords",
        title="Keyword settings",
        border_style="cyan",
    ))
    action = Prompt.ask(
        "Keyword action",
        choices=["A", "C", "S", "a", "c", "s"],
        default="S",
        show_choices=False,
    ).lower()
    if action == "s":
        console.print("[yellow]Keywords unchanged.[/]")
        return
    if action == "c":
        gs.keywords = []
        console.print("[green]Keywords cleared.[/]")
        return

    raw = Prompt.ask(
        "Keywords to add (comma-separated)",
        default="",
    )
    new_keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not new_keywords:
        console.print("[yellow]No keywords added.[/]")
        return
    existing = {k.lower() for k in gs.keywords}
    for keyword in new_keywords:
        key = keyword.lower()
        if key in existing:
            continue
        gs.keywords.append(keyword)
        existing.add(key)
    console.print(f"[green]Keywords set:[/] {', '.join(gs.keywords) or '(none)'}")


def _edit_location(gs: GlobalSettings) -> None:
    console.print(
        "\n[bold]Location instructions[/]\n"
        "  - Enter one location filter, for example United Kingdom, London, or Europe.\n"
        "  - Type [bold]CLEAR[/] to remove the location filter.\n"
        "  - Press [bold]Enter[/] without typing anything to keep the current location."
    )
    raw = Prompt.ask("Location", default="")
    if not raw.strip():
        console.print("[yellow]Location unchanged.[/]")
        return
    if raw.strip().lower() == "clear":
        gs.location = ""
        console.print("[green]Location filter cleared.[/]")
        return
    gs.location = raw.strip()
    console.print(f"[green]Location set:[/] {gs.location}")


def _edit_max_jobs(gs: GlobalSettings) -> None:
    console.print(
        "\n[bold]Max jobs instructions[/]\n"
        "  - This caps how many matched jobs are saved from each site per fetch.\n"
        "  - Higher values are broader but slower."
    )
    gs.max_jobs_per_site = IntPrompt.ask(
        "Max jobs per site",
        default=gs.max_jobs_per_site,
    )


# ---------------------------------------------------------------------------
# Site-management helpers
# ---------------------------------------------------------------------------

def _show_sites(cfg: Config) -> None:
    table = Table(title="Configured sites", border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("ID", style="bold yellow")
    table.add_column("Name")
    table.add_column("Scraper", style="cyan")
    table.add_column("Enabled", justify="center")
    table.add_column("URL", overflow="fold")
    for i, s in enumerate(cfg.sites, 1):
        table.add_row(
            str(i), s.id, s.name, s.scraper,
            "[green]✓[/]" if s.enabled else "[red]✗[/]",
            _display_site_url(s.url),
        )
    console.print(table)
    console.print(
        "[bold]A[/]dd  ·  [bold]E[/]dit  ·  [bold]R[/]emove  ·  "
        "[bold]T[/]oggle enable  ·  [bold]B[/]ack"
    )

def _display_site_url(url: str) -> str:
    return url.replace("{keyword}", "<global keywords>")


def _pick_site(cfg: Config) -> Site | None:
    if not cfg.sites:
        console.print("[yellow]No sites configured.[/]")
        return None
    n = IntPrompt.ask("Pick #", default=1)
    if 1 <= n <= len(cfg.sites):
        return cfg.sites[n - 1]
    console.print("[red]Out of range.[/]")
    return None


def _add_site(cfg: Config) -> None:
    console.print("\n[bold]Add new site[/]")
    sid = Prompt.ask("Short id (letters/numbers, no spaces)").strip().lower()
    if not sid or cfg.get_site(sid):
        console.print(f"[red]Invalid or duplicate id '{sid}'[/]")
        return
    name = Prompt.ask("Display name", default=sid.title())
    url = Prompt.ask("Search-results URL")
    console.print(f"Available scrapers: {', '.join(sorted(REGISTRY.keys()))}")
    scraper = Prompt.ask("Scraper", default="generic")
    enabled = Confirm.ask("Enabled?", default=True)
    cfg.add_site(Site(id=sid, name=name, scraper=scraper, url=url, enabled=enabled))
    console.print(f"[green]Added '{sid}'.[/]")


def _edit_site(cfg: Config) -> None:
    s = _pick_site(cfg)
    if s is None:
        return
    s.name = Prompt.ask("Name", default=s.name)
    s.url = Prompt.ask("Search URL", default=s.url)
    s.scraper = Prompt.ask(
        f"Scraper ({', '.join(sorted(REGISTRY.keys()))})",
        default=s.scraper,
    )
    s.enabled = Confirm.ask("Enabled?", default=s.enabled)
    console.print(f"[green]Updated '{s.id}'.[/]")


def _remove_site(cfg: Config) -> None:
    s = _pick_site(cfg)
    if s is None:
        return
    if Confirm.ask(f"Remove [bold red]{s.name}[/]?", default=False):
        cfg.remove_site(s.id)
        console.print(f"[green]Removed '{s.id}'.[/]")


def _toggle_site(cfg: Config) -> None:
    s = _pick_site(cfg)
    if s is None:
        return
    s.enabled = not s.enabled
    state = "[green]enabled[/]" if s.enabled else "[red]disabled[/]"
    console.print(f"'{s.id}' is now {state}.")


# ---------------------------------------------------------------------------
# Interactive menu loop
# ---------------------------------------------------------------------------

def interactive() -> None:
    _banner()
    while True:
        choice = _menu().lower()
        ns = argparse.Namespace(site=None, filter=None, debug=False)
        if choice == "1":
            cmd_fetch(ns)
        elif choice == "2":
            cmd_review(ns)
        elif choice == "3":
            cmd_list(ns)
        elif choice == "4":
            cmd_sites(ns)
        elif choice == "5":
            cmd_settings(ns)
        elif choice == "q":
            return
        console.print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobs", description="MSL Job Tracker")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    sub = parser.add_subparsers(dest="cmd")

    p_fetch = sub.add_parser("fetch", help="pull new jobs")
    p_fetch.add_argument("--site", help="only fetch from this site id")

    sub.add_parser("review", help="review unreviewed jobs")

    p_list = sub.add_parser("list", help="browse kept jobs")
    p_list.add_argument(
        "--filter",
        choices=["all", "applied", "not_applied"],
        help="filter to apply (skips the prompt)",
    )

    sub.add_parser("sites", help="manage sites")
    sub.add_parser("settings", help="edit global settings")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Make sure config exists (creates from default on first run)
    Config.load()

    if args.cmd == "fetch":
        cmd_fetch(args)
    elif args.cmd == "review":
        cmd_review(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "sites":
        cmd_sites(args)
    elif args.cmd == "settings":
        cmd_settings(args)
    else:
        interactive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
