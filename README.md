# MSL Job Tracker

A small, keyboard-driven terminal program for tracking Medical Science Liaison
(and other medical-affairs) jobs across pharma career sites.

It does three things:

1. **Fetch** — pull new job postings from configured career sites into a CSV,
   parsed into title / company / description / qualifications / deadline.
2. **Review** — flip through new postings card-by-card and keep / discard / skip.
   Kept jobs are saved to a separate CSV with an `applied` flag.
3. **List** — scroll your kept jobs (filter by all / applied / not-applied),
   press **Space** to toggle applied, **O** to open the posting in your browser.

It comes pre-loaded with three sites — Sanofi UK, MSD UK, GSK — and global
keyword/location defaults tuned for **MSL roles in the United Kingdom** with
oncology / immunology / neuroscience focus.

---

## One-time setup (macOS)

Open **Terminal** and paste these in:

```bash
# 1. cd into wherever you saved this folder
cd ~/Downloads/jobtracker        # adjust if you put it somewhere else

# 2. Create a virtual environment (keeps dependencies tidy)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

If `python3` isn't found, install it via Homebrew: `brew install python`.

## Running it

From the project folder, with the venv activated (`source .venv/bin/activate`):

```bash
python jobs.py            # opens the main menu
```

Or jump straight to a command:

```bash
python jobs.py fetch      # pull new jobs from all enabled sites
python jobs.py review     # review unreviewed jobs
python jobs.py list       # browse kept jobs
python jobs.py sites      # add / remove / edit sites
python jobs.py settings   # change global keywords / location
```

## Where your data lives

Everything stays on your Mac, in the `data/` folder next to `jobs.py`:

- `data/fetched.csv` — every job ever fetched, with a `reviewed` column.
- `data/kept.csv` — jobs you kept, with an `applied` column.
- `config.json` — your sites and global keyword/location defaults.

You can open these CSVs in Excel or Numbers anytime. The program only ever
appends to `fetched.csv` (deduped by URL), so re-running `fetch` won't make
duplicates.

## Adding a new site

```bash
python jobs.py sites
```

…and pick "Add site". You'll be asked for:

- A short name (e.g. "AstraZeneca")
- The search-results URL on that site
- Which scraper to use (`generic`, or one of the per-platform ones if you know
  it — Workday, Phenom, etc.)

The `generic` scraper does best-effort link discovery and parsing; the
per-platform scrapers are more accurate but only work on sites built on that
platform.

## Keyboard shortcuts

**Review screen**

- `K` — keep this job
- `D` — discard this job
- `S` — skip (decide later — stays unreviewed)
- `Q` — quit review

**List screen**

- `↑` / `↓` — scroll
- `Space` — toggle applied / not applied
- `O` — open the job posting in your default browser
- `Q` — quit
- `A` — show all
- `Y` — show applied only
- `N` — show not-applied only

## Troubleshooting scraping

Career sites change their HTML often. If a fetch returns 0 jobs from a site you
expect to have results, try:

1. `python jobs.py fetch --site sanofi --debug` — prints what it found.
2. Open `config.json` and update the search URL to a more specific one.
3. Switch the scraper to `generic` if a per-platform one stops working.
