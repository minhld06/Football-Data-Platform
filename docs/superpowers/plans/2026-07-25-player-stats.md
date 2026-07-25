# Player Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add goals (statbunker) and xG/xA/assists (understat) for players, joined onto the `player_id` identity anchor from sub-project 1, ending in a queryable `gold.player_performance` table.

**Architecture:** Two crawler additions (statbunker per-club top-scorers loop, understat second-table parse on the already-loaded league page) land raw JSON in bronze under a new `entity_type='player_stats'`. Two new staging models resolve each source's raw player/team name strings to `player_id`/`team_id` — first via an exception seed (`player_name_map.csv`), falling back to a normalized-name match against `silver.players` — using a new `unaccent`-based dbt macro. `gold.player_performance` left-joins `silver.players` (base) to latest-snapshot-deduped versions of both staging models directly, without an intermediate silver table, mirroring how `stg_understat__standings` feeds `gold.league_standings` today.

**Tech Stack:** Python (`requests`, `BeautifulSoup`, `playwright.sync_api`), dbt-core + dbt-postgres, PostgreSQL `unaccent` extension.

This plan implements
[`docs/superpowers/specs/2026-07-25-player-stats-design.md`](../specs/2026-07-25-player-stats-design.md).
Read that spec's "Context" section first — it documents the actual page
structures (statbunker's per-club top-scorers URL, understat's 4th-table
layout) found by live inspection before this plan was written.

## Global Constraints

- Crawlers must rate-limit requests to the same host — every new request-making
  function calls `limiter.wait()` before its request (see CLAUDE.md Week 2 rule:
  "no aggressive or parallel crawling of the same host").
- Never join gold/silver tables on team or player *names* — `team_id`/`player_id`
  are the only stable cross-source keys (CLAUDE.md, `docs/gold_data_contract.md`).
- A single bad record/file may be skipped with logging; config/DB/schema errors
  fail fast (CLAUDE.md error-handling rule).
- Keep `docs/gold_data_contract.md` in sync with any gold schema change.
- Run all dbt commands from the `transform/` directory.

---

### Task 1: statbunker crawler — per-club top scorers

**Files:**
- Modify: `crawlers/statbunker/scraper.py`

**Interfaces:**
- Produces: `get_top_scorers(comp_id, club_id) -> list[dict]`, each dict has
  keys `player, goals, fh, sh, fs, ls, h, a` (all string values, unconverted —
  matches how `get_standings` returns strings for `rank`/`played`/etc.).
  `get_standings(comp_id) -> list[dict]` now also includes a `"club_id"` key
  per row (string, or `None` if not found).

- [ ] **Step 1: Add `club_id` extraction to `get_standings()`**

Add the import at the top of the file (after the existing `from crawlers.common.utils import ...` line):

```python
from urllib.parse import urlparse, parse_qs
```

Replace the row-building block inside `get_standings()`:

```python
        # Team name is inside a <p> tag within the 2nd column
        team_tag = cols[1].find("p")
        if not team_tag:
            continue

        standings.append({
            "rank":           cols[0].get_text(strip=True),
            "team":           team_tag.get_text(strip=True),
            "played":         cols[2].get_text(strip=True),
            "wins":           cols[3].get_text(strip=True),
            "draws":          cols[4].get_text(strip=True),
            "losses":         cols[5].get_text(strip=True),
            "goals_for":      cols[6].get_text(strip=True),
            "goals_against":  cols[7].get_text(strip=True),
            "goal_diff":      cols[8].get_text(strip=True),
            "points":         cols[9].get_text(strip=True),
        })
```

with:

```python
        # Team name is inside a <p> tag within the 2nd column; the <a> wrapping
        # it links to that club's own pages and carries club_id in its href —
        # this is the only place club_id is exposed, there's no separate lookup.
        team_tag = cols[1].find("p")
        if not team_tag:
            continue

        team_link = cols[1].find("a")
        club_id = None
        if team_link and team_link.get("href"):
            query = parse_qs(urlparse(team_link["href"]).query)
            club_id = query.get("club_id", [None])[0]

        standings.append({
            "rank":           cols[0].get_text(strip=True),
            "team":           team_tag.get_text(strip=True),
            "club_id":        club_id,
            "played":         cols[2].get_text(strip=True),
            "wins":           cols[3].get_text(strip=True),
            "draws":          cols[4].get_text(strip=True),
            "losses":         cols[5].get_text(strip=True),
            "goals_for":      cols[6].get_text(strip=True),
            "goals_against":  cols[7].get_text(strip=True),
            "goal_diff":      cols[8].get_text(strip=True),
            "points":         cols[9].get_text(strip=True),
        })
```

- [ ] **Step 2: Add `get_top_scorers()`**

Add this new function after `get_standings()` (before `crawl_competition()`):

```python
def get_top_scorers(comp_id, club_id):
    """Scrape one club's top goal scorers. statbunker has no competition-wide
    top-scorers page — this must be called once per club_id."""
    url = f"{BASE_URL}/competitions/TopGoalScorers?comp_id={comp_id}&club_id={club_id}"

    limiter.wait()
    response = retry_request(url, headers=HEADERS, timeout=30)
    if not response:
        logger.error(f"Failed to fetch top scorers for comp_id={comp_id} club_id={club_id}")
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"class": "table"})
    if not table:
        logger.error(f"Top scorers table not found for comp_id={comp_id} club_id={club_id}")
        return []

    tbody = table.find("tbody")
    if not tbody:
        logger.error(f"Top scorers table has no tbody for comp_id={comp_id} club_id={club_id}")
        return []

    player_stats = []
    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        # Player name is inside a <p> tag within the 1st column, same structure
        # as the team name on the standings page.
        player_tag = cols[0].find("p")
        if not player_tag:
            continue

        player_stats.append({
            "player":  player_tag.get_text(strip=True),
            "goals":   cols[1].get_text(strip=True),
            "fh":      cols[2].get_text(strip=True),
            "sh":      cols[3].get_text(strip=True),
            "fs":      cols[4].get_text(strip=True),
            "ls":      cols[5].get_text(strip=True),
            "h":       cols[6].get_text(strip=True),
            "a":       cols[7].get_text(strip=True),
        })

    return player_stats
```

- [ ] **Step 3: Wire the per-club loop into `crawl_competition()`**

Replace `crawl_competition()`:

```python
def crawl_competition(competition_code, season):
    logger.info(f"Starting crawl for {competition_code} season {season}...")
    key = f"{competition_code}_{season}"
    comp_id = COMPETITION_IDS.get(key)
    if not comp_id:
        logger.error(f"comp_id not found for {key}")
        return

    standings = get_standings(comp_id)
    if not standings:
        logger.error(f"Skipping file save for {key} because standings could not be fetched")
        limiter.wait()
        return

    save_raw(standings, "statbunker", "standings", f"{competition_code}_{season}")

    logger.info(f"Finished {competition_code} season {season}")
    limiter.wait()
```

with:

```python
def crawl_competition(competition_code, season):
    logger.info(f"Starting crawl for {competition_code} season {season}...")
    key = f"{competition_code}_{season}"
    comp_id = COMPETITION_IDS.get(key)
    if not comp_id:
        logger.error(f"comp_id not found for {key}")
        return

    standings = get_standings(comp_id)
    if not standings:
        logger.error(f"Skipping file save for {key} because standings could not be fetched")
        limiter.wait()
        return

    save_raw(standings, "statbunker", "standings", f"{competition_code}_{season}")

    for team in standings:
        club_id = team.get("club_id")
        if not club_id:
            logger.error(f"Skipping top scorers for {team['team']} ({key}) — no club_id found")
            continue

        player_stats = get_top_scorers(comp_id, club_id)
        if not player_stats:
            logger.error(f"Skipping top scorers save for {team['team']} ({key}) because no data was fetched")
            continue

        # The top-scorers page is pre-scoped to one club and has no team column —
        # stamp the team name we already know from the loop onto every row.
        for player in player_stats:
            player["team"] = team["team"]

        save_raw(player_stats, "statbunker", "player_stats", f"{competition_code}_{season}_{club_id}")

    logger.info(f"Finished {competition_code} season {season}")
    limiter.wait()
```

- [ ] **Step 4: Run it and verify the output**

```bash
python crawlers/statbunker/scraper.py
```

Then check that files were created — one standings file plus one player_stats
file per club (20 for Premier League):

```bash
Get-ChildItem -Recurse "data/raw/statbunker/player_stats" -Filter *.json | Measure-Object
```

Expected: `Count` is 20. Open one file (e.g. the Arsenal one, `club_id=5`) and
confirm every row has `player`, `goals`, `fh`, `sh`, `fs`, `ls`, `h`, `a`,
`team` keys, and `team` matches the club the file is named after.

- [ ] **Step 5: Ingest and verify bronze rows**

Requires Postgres running (`docker compose up -d`) and `DATABASE_URL` set.

```bash
python ingestion/ingest.py --source statbunker
```

Then, using `psql` or pgAdmin:

```sql
select entity_type, count(*) from bronze.raw_documents where source = 'statbunker' group by entity_type;
```

Expected: a `player_stats` row with count 20 (one per club), alongside the
existing `standings` row.

- [ ] **Step 6: Commit**

```bash
git add crawlers/statbunker/scraper.py
git commit -m "feat: crawl statbunker top scorers per club"
```

---

### Task 2: understat crawler — player xG/xA from the same page

> **Amended during execution.** The steps below (parsing the 4th `<table>`
> on the rendered league page) were implemented and run, but a follow-up live
> check found that table is **client-side paginated at 10 rows/page**
> (confirmed via its `ul.pagination` widget: `«12345...54»`, ~54 pages ≈ 540
> players) — the crawl only ever captured page 1 (10 players), not the full
> roster. The actual fix: Understat's front-end fetches the *complete*
> dataset from `https://understat.com/getLeagueData/{league}/{season}`
> (header `X-Requested-With: XMLHttpRequest` required) and paginates it
> client-side purely for display. `get_player_stats()` was rewritten to call
> that JSON endpoint directly via `requests`/`retry_request` — no Playwright,
> no HTML parsing, no pagination — returning raw records shaped `id,
> player_name, games, time, goals, xG, assists, xA, shots, key_passes,
> yellow_cards, red_cards, position, team_title, npg, npxG, xGChain,
> xGBuildup` (field names differ from the `player/team/apps/minutes/xg/xa/
> xg90/xa90` shape assumed below — Task 6 reflects the real field names).
> `get_standings()` is untouched — its table isn't paginated (only 20 rows).
> See `crawlers/understat/scraper.py` for the final code; the steps below are
> kept for the historical record of how the bug was found, not as something
> to redo.

**Files:**
- Modify: `crawlers/understat/scraper.py`

**Interfaces:**
- Produces: `get_player_stats(league, season) -> list[dict]`, each dict has
  keys `player, team, apps, minutes, goals, assists, xg, xa, xg90, xa90`
  (strings, unconverted). `get_standings(league, season)` behavior is
  unchanged (same return shape as before).
- Internal helpers `_fetch_league_page_html(league, season) -> str | None`,
  `_parse_standings_table(html, league, season) -> list[dict]`,
  `_parse_player_stats_table(html, league, season) -> list[dict]` — used by
  `crawl_competition()` to fetch the page once and parse both tables from it.

- [ ] **Step 1: Split HTML fetching out of `get_standings()`**

Replace the entire current `get_standings()` function:

```python
def get_standings(league, season):
    """Scrape the standings table + xG from Understat using Playwright"""
    season_start = season.split("-")[0]
    url = f"{BASE_URL}/league/{league}/{season_start}"

    browser = None
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
        except Exception as e:
            logger.error(f"Playwright error while crawling {url}: {e}")
            return []
        finally:
            if browser:
                browser.close()

    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        # The standings table is always the first table (index 0)
        table = tables[0] if tables else None
        if not table:
            logger.error(f"Table not found for {league} season {season}!")
            return []

        standings = []
        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 11:
                continue

            # Team name is inside an <a> tag
            team_tag = cols[1].find("a")

            # xG has an extra <sup> tag inside — use get_text() to grab everything then split it out
            xg_text = cols[9].find("sup")
            xga_text = cols[10].find("sup")
            xpts_text = cols[11].find("sup") if len(cols) > 11 else None

            standings.append({
                "rank":     cols[0].get_text(strip=True),
                "team":     team_tag.get_text(strip=True) if team_tag else "",
                "played":   cols[2].get_text(strip=True),
                "wins":     cols[3].get_text(strip=True),
                "draws":    cols[4].get_text(strip=True),
                "losses":   cols[5].get_text(strip=True),
                "goals_for":     cols[6].get_text(strip=True),
                "goals_against": cols[7].get_text(strip=True),
                "points":   cols[8].get_text(strip=True),
                # Extract the xG figure — strip the <sup> (+/-) part by splitting it off
                "xG":  cols[9].get_text(strip=True).split("+")[0].split("-")[0] if xg_text else cols[9].get_text(strip=True),
                "xGA": cols[10].get_text(strip=True).split("+")[0].split("-")[0] if xga_text else cols[10].get_text(strip=True),
                "xPTS": cols[11].get_text(strip=True).split("+")[0].split("-")[0] if xpts_text else "",
            })
    except AttributeError as e:
        logger.error(f"HTML structure changed while parsing {league} season {season}: {e}")
        return []

    return standings
```

with these four functions (fetch, two parsers, and the now-thin public
`get_standings`):

```python
def _fetch_league_page_html(league, season):
    """Load the Understat league page once via Playwright. Both the standings
    table and the player-stats table live on this same page — callers parse
    it as many times as needed without re-fetching."""
    season_start = season.split("-")[0]
    url = f"{BASE_URL}/league/{league}/{season_start}"

    browser = None
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)
            return page.content()
        except Exception as e:
            logger.error(f"Playwright error while crawling {url}: {e}")
            return None
        finally:
            if browser:
                browser.close()


def _parse_standings_table(html, league, season):
    """Parse the standings + xG table — the 1st <table> on the league page."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        table = tables[0] if tables else None
        if not table:
            logger.error(f"Table not found for {league} season {season}!")
            return []

        standings = []
        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 11:
                continue

            # Team name is inside an <a> tag
            team_tag = cols[1].find("a")

            # xG has an extra <sup> tag inside — use get_text() to grab everything then split it out
            xg_text = cols[9].find("sup")
            xga_text = cols[10].find("sup")
            xpts_text = cols[11].find("sup") if len(cols) > 11 else None

            standings.append({
                "rank":     cols[0].get_text(strip=True),
                "team":     team_tag.get_text(strip=True) if team_tag else "",
                "played":   cols[2].get_text(strip=True),
                "wins":     cols[3].get_text(strip=True),
                "draws":    cols[4].get_text(strip=True),
                "losses":   cols[5].get_text(strip=True),
                "goals_for":     cols[6].get_text(strip=True),
                "goals_against": cols[7].get_text(strip=True),
                "points":   cols[8].get_text(strip=True),
                # Extract the xG figure — strip the <sup> (+/-) part by splitting it off
                "xG":  cols[9].get_text(strip=True).split("+")[0].split("-")[0] if xg_text else cols[9].get_text(strip=True),
                "xGA": cols[10].get_text(strip=True).split("+")[0].split("-")[0] if xga_text else cols[10].get_text(strip=True),
                "xPTS": cols[11].get_text(strip=True).split("+")[0].split("-")[0] if xpts_text else "",
            })
    except AttributeError as e:
        logger.error(f"HTML structure changed while parsing {league} season {season}: {e}")
        return []

    return standings


def _parse_player_stats_table(html, league, season):
    """Parse the player xG/xA table — the 4th <table> on the league page
    (index 3), a completely separate table from standings (index 0)."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        table = tables[3] if len(tables) > 3 else None
        if not table:
            logger.error(f"Player stats table not found for {league} season {season}!")
            return []

        player_stats = []
        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 11:
                continue

            # Player and team names are each inside an <a> tag. A player
            # transferred mid-season shows multiple <a> tags comma-joined in
            # the team cell (e.g. "Bournemouth, Manchester City") — get_text()
            # captures that whole string as-is; resolving it is a staging concern.
            player_tag = cols[1].find("a")

            # xG/xA have an extra <sup> tag inside, same +/- quirk as standings
            xg_text = cols[7].find("sup")
            xa_text = cols[8].find("sup")

            player_stats.append({
                "player":  player_tag.get_text(strip=True) if player_tag else cols[1].get_text(strip=True),
                "team":    cols[2].get_text(strip=True),
                "apps":    cols[3].get_text(strip=True),
                "minutes": cols[4].get_text(strip=True),
                "goals":   cols[5].get_text(strip=True),
                "assists": cols[6].get_text(strip=True),
                "xg":  cols[7].get_text(strip=True).split("+")[0].split("-")[0] if xg_text else cols[7].get_text(strip=True),
                "xa":  cols[8].get_text(strip=True).split("+")[0].split("-")[0] if xa_text else cols[8].get_text(strip=True),
                "xg90":    cols[9].get_text(strip=True),
                "xa90":    cols[10].get_text(strip=True),
            })
    except AttributeError as e:
        logger.error(f"HTML structure changed while parsing player stats for {league} season {season}: {e}")
        return []

    return player_stats


def get_standings(league, season):
    """Scrape the standings table + xG from Understat using Playwright"""
    html = _fetch_league_page_html(league, season)
    if html is None:
        return []
    return _parse_standings_table(html, league, season)


def get_player_stats(league, season):
    """Scrape the player xG/xA table from Understat using Playwright"""
    html = _fetch_league_page_html(league, season)
    if html is None:
        return []
    return _parse_player_stats_table(html, league, season)
```

- [ ] **Step 2: Update `crawl_competition()` to fetch the page once for both tables**

Replace:

```python
def crawl_competition(league, season):
    """Crawl one competition and save the results"""
    logger.info(f"Starting crawl for {league} season {season}...")
    standings = get_standings(league, season)
    if not standings:
        logger.error(f"Skipping file save for {league} season {season} because standings could not be fetched")
        limiter.wait()
        return

    save_raw(standings, "understat", "standings", f"{league}_{season}")
    limiter.wait()
    logger.info(f"Finished {league} season {season}")
```

with:

```python
def crawl_competition(league, season):
    """Crawl one competition and save the results"""
    logger.info(f"Starting crawl for {league} season {season}...")

    html = _fetch_league_page_html(league, season)
    if html is None:
        logger.error(f"Skipping file save for {league} season {season} because the page could not be fetched")
        limiter.wait()
        return

    standings = _parse_standings_table(html, league, season)
    if not standings:
        logger.error(f"Skipping standings save for {league} season {season} because no data was parsed")
    else:
        save_raw(standings, "understat", "standings", f"{league}_{season}")

    player_stats = _parse_player_stats_table(html, league, season)
    if not player_stats:
        logger.error(f"Skipping player stats save for {league} season {season} because no data was parsed")
    else:
        save_raw(player_stats, "understat", "player_stats", f"{league}_{season}")

    limiter.wait()
    logger.info(f"Finished {league} season {season}")
```

- [ ] **Step 3: Run it and verify the output**

```bash
python crawlers/understat/scraper.py
```

Check both new files exist:

```bash
Get-ChildItem -Recurse "data/raw/understat/player_stats" -Filter *.json
```

Expected: one file for `EPL_2025-2026` and one for `Ligue_1_2025-2026`. Open
the EPL one and confirm rows have `player, team, apps, minutes, goals,
assists, xg, xa, xg90, xa90` keys, `xg`/`xa` are plain decimal strings (no
`+`/`-` suffix), and at least one row's `team` contains a comma (a mid-season
transfer — if none do this season, that's fine, just confirm the format looks
right for players who didn't transfer).

- [ ] **Step 4: Ingest and verify bronze rows**

```bash
python ingestion/ingest.py --source understat
```

```sql
select entity_type, count(*) from bronze.raw_documents where source = 'understat' group by entity_type;
```

Expected: a `player_stats` row count of 2 (EPL + Ligue 1), alongside the
existing `standings` rows.

- [ ] **Step 5: Commit**

```bash
git add crawlers/understat/scraper.py
git commit -m "feat: crawl understat player xG/xA from the existing league page"
```

(Superseded by a follow-up commit, `fix: crawl understat player stats via
JSON endpoint instead of paginated HTML table` — see the amendment note at
the top of this task.)

---

### Task 3: Enable `unaccent` + add the name-normalization macro

**Files:**
- Create: `infra/postgres/migrations/004_enable_unaccent_extension.sql`
- Create: `transform/macros/normalize_player_name.sql`

**Interfaces:**
- Produces: dbt macro `normalize_player_name(column_name)` — Jinja macro
  usable in any model as `{{ normalize_player_name('some.column') }}`,
  expanding to a SQL expression (`lower(regexp_replace(unaccent(...), ...))`).
  Requires the Postgres `unaccent` extension to be enabled in the target
  database (done by the migration, not by dbt).

- [ ] **Step 1: Write the migration**

```sql
-- =========================================================
-- Enable the unaccent extension (used by normalize_player_name macro)
-- Football Data Platform
-- =========================================================
-- Lets dbt models strip accents when matching player names across sources
-- (e.g. statbunker's "Gyokeres" vs a possible accented understat spelling),
-- without maintaining a fully manual name-mapping seed for ~600+ players.

CREATE EXTENSION IF NOT EXISTS unaccent;
```

Save as `infra/postgres/migrations/004_enable_unaccent_extension.sql`.

- [ ] **Step 2: Apply the migration**

```bash
psql -U postgres -d football -f infra/postgres/migrations/004_enable_unaccent_extension.sql
```

Expected output: `CREATE EXTENSION`.

- [ ] **Step 3: Write the macro**

```sql
{% macro normalize_player_name(column_name) %}
    lower(regexp_replace(unaccent({{ column_name }}), '[^a-z0-9]+', ' ', 'g'))
{% endmacro %}
```

Save as `transform/macros/normalize_player_name.sql`.

- [ ] **Step 4: Verify the macro compiles**

From `transform/`:

```bash
dbt run-operation normalize_player_name --args '{column_name: "player_name"}'
```

Expected: prints the expanded SQL (`lower(regexp_replace(unaccent(player_name), '[^a-z0-9]+', ' ', 'g'))`)
with no Jinja errors. (This macro isn't a model, so there's nothing to query
yet — Tasks 5/6 are what actually exercise it against real data.)

- [ ] **Step 5: Commit**

```bash
git add infra/postgres/migrations/004_enable_unaccent_extension.sql transform/macros/normalize_player_name.sql
git commit -m "feat: enable unaccent extension and add normalize_player_name macro"
```

---

### Task 4: `player_name_map` seed

**Files:**
- Create: `transform/seeds/player_name_map.csv`
- Modify: `transform/dbt_project.yml`

**Interfaces:**
- Produces: dbt seed `player_name_map` — referenceable as `{{ ref('player_name_map') }}`,
  columns `source (text), raw_player_name (text), team_id (integer), player_id (integer)`.

- [ ] **Step 1: Create the seed file**

```csv
source,raw_player_name,team_id,player_id
```

Save as `transform/seeds/player_name_map.csv`. This is intentionally
header-only — see
[the spec](../specs/2026-07-25-player-stats-design.md#seed--transformseedsplayer_name_mapcsv)
for why this isn't a full manual roster like `team_name_map.csv`. Rows get
added reactively in Task 10 once `assert_player_names_mapped` (Task 7)
surfaces real unmatched names.

- [ ] **Step 2: Pin column types**

An empty (header-only) CSV gives dbt-postgres no data to infer types from, so
without this config `dbt seed` would create `team_id`/`player_id` as `TEXT`,
which would fail to compare against the `INTEGER` columns in Task 5/6's
staging models (`operator does not exist: integer = text`). Add to
`transform/dbt_project.yml`, after the existing `models:` block:

```yaml
seeds:
  transform:
    player_name_map:
      +column_types:
        team_id: integer
        player_id: integer
```

- [ ] **Step 3: Load the seed and verify column types**

From `transform/`:

```bash
dbt seed --select player_name_map
```

Expected: `1 of 1 OK loaded seed file ... player_name_map`. Then verify types
(seeds have no schema override in this project, so — per
`transform/profiles.yml`'s `schema: silver` and the default
`generate_schema_name` macro — they land in the `silver` schema, same as
`team_name_map`):

```sql
select column_name, data_type
from information_schema.columns
where table_schema = 'silver' and table_name = 'player_name_map';
```

Expected: `team_id` and `player_id` show `integer`, not `text`.

- [ ] **Step 4: Commit**

```bash
git add transform/seeds/player_name_map.csv transform/dbt_project.yml
git commit -m "feat: add empty player_name_map seed with pinned column types"
```

---

### Task 5: `stg_statbunker__player_stats` staging model

**Files:**
- Create: `transform/models/staging/stg_statbunker__player_stats.sql`
- Modify: `transform/models/staging/_staging.yml`

**Interfaces:**
- Consumes: `source('bronze', 'raw_documents')` filtered to
  `source='statbunker', entity_type='player_stats'`; `ref('team_name_map')`;
  `ref('player_name_map')`; `ref('players')` (silver, from sub-project 1,
  columns `player_id, player_name, team_id`); macro `normalize_player_name`.
- Produces: model `stg_statbunker__player_stats` with columns `season,
  league, ingestion_time, team_id, raw_player_name, player_id, goals, fh, sh,
  fs, ls, h, a`. `team_id`/`player_id` may be `NULL` (unmapped team/player).

- [ ] **Step 1: Write the model**

```sql
with player_stats_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'statbunker'
      and entity_type = 'player_stats'
),

player_stats_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload) as row_json
    from player_stats_raw
),

resolved_team as (
    select
        r.season,
        r.league,
        r.ingestion_time,
        r.row_json ->> 'player' as raw_player_name,
        m.team_id,
        (r.row_json ->> 'goals')::int as goals,
        (r.row_json ->> 'fh')::int as fh,
        (r.row_json ->> 'sh')::int as sh,
        (r.row_json ->> 'fs')::int as fs,
        (r.row_json ->> 'ls')::int as ls,
        (r.row_json ->> 'h')::int as h,
        (r.row_json ->> 'a')::int as a
    from player_stats_rows r
    left join {{ ref('team_name_map') }} m
        on m.source = 'statbunker'
       and m.raw_team_name = r.row_json ->> 'team'
)

select
    rt.season,
    rt.league,
    rt.ingestion_time,
    rt.team_id,
    rt.raw_player_name,
    coalesce(pm.player_id, sp.player_id) as player_id,
    rt.goals,
    rt.fh,
    rt.sh,
    rt.fs,
    rt.ls,
    rt.h,
    rt.a
from resolved_team rt
left join {{ ref('player_name_map') }} pm
    on pm.source = 'statbunker'
   and pm.raw_player_name = rt.raw_player_name
   and pm.team_id = rt.team_id
left join {{ ref('players') }} sp
    on {{ normalize_player_name('sp.player_name') }} = {{ normalize_player_name('rt.raw_player_name') }}
   and sp.team_id = rt.team_id
```

Save as `transform/models/staging/stg_statbunker__player_stats.sql`.

- [ ] **Step 2: Add schema entry**

Add to `transform/models/staging/_staging.yml`, after the
`stg_football_data_org__players` entry:

```yaml
  - name: stg_statbunker__player_stats
    description: "Staging model for StatBunker top-scorer data. Grain is 1 row/player/snapshot.
                  Scraped per-club (statbunker has no competition-wide top-scorers page). team_id
                  resolved via team_name_map.csv; player_id resolved via player_name_map.csv
                  (exceptions) falling back to a normalize_player_name() match against silver.players.
                  Both can be NULL if the team/player name isn't mapped — see
                  assert_player_names_mapped and docs/gold_data_contract.md. No not_null test on
                  player_id here on purpose: unmatched names are expected often enough (new signings,
                  transfers) that a hard-failing schema test would block routine dbt build runs — the
                  warn-severity assert_player_names_mapped test is the intended way to surface gaps."
    columns:
      - name: raw_player_name
        tests:
          - not_null
```

- [ ] **Step 3: Run and verify**

```bash
dbt run --select stg_statbunker__player_stats
```

Expected: `1 of 1 OK created sql view model ... stg_statbunker__player_stats`.
Then spot-check (staging models have no schema override, so — like all other
staging models — this lands in the `silver` schema, per
`transform/profiles.yml`):

```sql
select * from silver.stg_statbunker__player_stats order by goals desc nulls last limit 10;
select count(*) filter (where player_id is null) as unmatched, count(*) as total
from silver.stg_statbunker__player_stats;
```

Expected: top rows are recognizable high-goal players (e.g. a Manchester
City or Arsenal forward), and `unmatched` is a small fraction of `total`, not
most of it — a large unmatched count would mean `normalize_player_name`
isn't working as expected and is worth investigating before continuing.

- [ ] **Step 4: Commit**

```bash
git add transform/models/staging/stg_statbunker__player_stats.sql transform/models/staging/_staging.yml
git commit -m "feat: add stg_statbunker__player_stats staging model"
```

---

### Task 6: `stg_understat__player_stats` staging model

> **Amended per Task 2's correction.** Raw field names come from Understat's
> `getLeagueData` JSON endpoint, not the HTML table shape assumed when this
> plan was first written: `player_name` (not `player`), `team_title` (not
> `team`), `games` (not `apps`), `time` (not `minutes`), `xG`/`xA` (capitalized,
> not `xg`/`xa`). The endpoint also doesn't return `xg90`/`xa90` directly (the
> on-page table computes those client-side) — this model derives them as
> `xg / (minutes / 90)`, matching the site's own formula. Output column names
> (`apps, minutes, xg, xa, xg90, xa90`, etc.) are unchanged from the original
> plan, so Task 8's gold model needs no changes.

**Files:**
- Create: `transform/models/staging/stg_understat__player_stats.sql`
- Modify: `transform/models/staging/_staging.yml`

**Interfaces:**
- Consumes: same as Task 5, but `source='understat'`.
- Produces: model `stg_understat__player_stats` with columns `season, league,
  ingestion_time, team_id, raw_player_name, player_id, apps, minutes, goals,
  assists, xg, xa, xg90, xa90`. A comma-joined `team_title` value (mid-season
  transfer, e.g. `"Bournemouth,Manchester City"`) naturally fails the
  `team_name_map` join (no single team name in the seed matches a multi-team
  string), leaving `team_id`/`player_id` `NULL` — no special-case code needed
  for this.

- [ ] **Step 1: Write the model**

```sql
with player_stats_raw as (
    select season, league, ingestion_time, payload
    from {{ source('bronze', 'raw_documents') }}
    where source = 'understat'
      and entity_type = 'player_stats'
),

player_stats_rows as (
    select
        season,
        league,
        ingestion_time,
        jsonb_array_elements(payload) as row_json
    from player_stats_raw
),

resolved_team as (
    select
        r.season,
        r.league,
        r.ingestion_time,
        r.row_json ->> 'player_name' as raw_player_name,
        m.team_id,
        (r.row_json ->> 'games')::int as apps,
        (r.row_json ->> 'time')::int as minutes,
        (r.row_json ->> 'goals')::int as goals,
        (r.row_json ->> 'assists')::int as assists,
        (r.row_json ->> 'xG')::numeric as xg,
        (r.row_json ->> 'xA')::numeric as xa
    from player_stats_rows r
    left join {{ ref('team_name_map') }} m
        on m.source = 'understat'
       and m.raw_team_name = r.row_json ->> 'team_title'
)

select
    rt.season,
    rt.league,
    rt.ingestion_time,
    rt.team_id,
    rt.raw_player_name,
    coalesce(pm.player_id, sp.player_id) as player_id,
    rt.apps,
    rt.minutes,
    rt.goals,
    rt.assists,
    rt.xg,
    rt.xa,
    -- Understat's JSON endpoint gives season totals only, not the per-90
    -- rates its own on-page table computes client-side — derive them the
    -- same way: xG / (minutes / 90). NULL when minutes is 0.
    round(rt.xg / nullif(rt.minutes, 0)::numeric * 90, 3) as xg90,
    round(rt.xa / nullif(rt.minutes, 0)::numeric * 90, 3) as xa90
from resolved_team rt
left join {{ ref('player_name_map') }} pm
    on pm.source = 'understat'
   and pm.raw_player_name = rt.raw_player_name
   and pm.team_id = rt.team_id
left join {{ ref('players') }} sp
    on {{ normalize_player_name('sp.player_name') }} = {{ normalize_player_name('rt.raw_player_name') }}
   and sp.team_id = rt.team_id
```

Save as `transform/models/staging/stg_understat__player_stats.sql`.

- [ ] **Step 2: Add schema entry**

Add to `transform/models/staging/_staging.yml`, after the
`stg_statbunker__player_stats` entry from Task 5:

```yaml
  - name: stg_understat__player_stats
    description: "Staging model for Understat player stats, fetched from Understat's own JSON data
                  endpoint (getLeagueData/{league}/{season}) rather than scraped from the on-page
                  table — that table is client-side paginated at 10 rows/page (~50+ pages for a full
                  league), so the endpoint is used directly to get the full roster in one response.
                  xg90/xa90 are derived (xg / (minutes/90)) since the endpoint doesn't return them
                  directly. Grain is 1 row/player/snapshot. team_id/player_id resolution is the same
                  as stg_statbunker__player_stats. A player transferred mid-season shows a
                  comma-joined team string on understat (e.g. 'Bournemouth,Manchester City'), which
                  intentionally fails the team_name_map join and leaves team_id/player_id NULL rather
                  than guessing which team is current — see docs/gold_data_contract.md."
    columns:
      - name: raw_player_name
        tests:
          - not_null
```

- [ ] **Step 3: Run and verify**

```bash
dbt run --select stg_understat__player_stats
```

```sql
select * from silver.stg_understat__player_stats order by xg desc nulls last limit 10;
select count(*) filter (where team_id is null) as unmapped_team, count(*) filter (where player_id is null) as unmatched_player, count(*) as total
from silver.stg_understat__player_stats;
```

Expected: top rows by `xg` are recognizable high-output attackers, and
`xg90` values are plausible (e.g. Haaland ≈ 0.87). A large chunk of
`unmatched_player` is expected and not a bug: `silver.players` (from
sub-project 1) is Premier-League-only, so every Ligue 1 row in this model
can never resolve a `player_id` — check the ratio against
`(total - EPL row count)` before assuming something's wrong. `unmapped_team`
should be small (mid-season-transfer rows, or teams outside
`team_name_map.csv`).

- [ ] **Step 4: Commit**

```bash
git add transform/models/staging/stg_understat__player_stats.sql transform/models/staging/_staging.yml
git commit -m "feat: add stg_understat__player_stats staging model"
```

---

### Task 7: `assert_player_names_mapped` test

**Files:**
- Create: `transform/tests/assert_player_names_mapped.sql`

**Interfaces:**
- Consumes: `ref('stg_statbunker__player_stats')`, `ref('stg_understat__player_stats')`.
- Produces: a dbt singular test, `severity='warn'` — surfaces unmatched
  `(source, raw_player_name)` pairs without failing `dbt build`.

- [ ] **Step 1: Write the test**

```sql
{{ config(severity='warn') }}

select source, raw_player_name
from (
    select 'statbunker' as source, raw_player_name, player_id
    from {{ ref('stg_statbunker__player_stats') }}

    union all

    select 'understat' as source, raw_player_name, player_id
    from {{ ref('stg_understat__player_stats') }}
) unmapped_check
where player_id is null
```

Save as `transform/tests/assert_player_names_mapped.sql`.

- [ ] **Step 2: Run it and inspect real gaps**

```bash
dbt test --select assert_player_names_mapped
```

Expected: dbt reports the test as `WARN` (not `ERROR`, and not blocking) if
any rows come back, or `PASS` if every name matched. Either way, run the
underlying query directly to see which names it's flagging (used again in
Task 10):

```sql
select source, raw_player_name
from (
    select 'statbunker' as source, raw_player_name, player_id
    from silver.stg_statbunker__player_stats

    union all

    select 'understat' as source, raw_player_name, player_id
    from silver.stg_understat__player_stats
) unmapped_check
where player_id is null;
```

- [ ] **Step 3: Commit**

```bash
git add transform/tests/assert_player_names_mapped.sql
git commit -m "test: warn on unmapped player names in statbunker/understat player stats"
```

---

### Task 8: `gold.player_performance`

**Files:**
- Create: `transform/models/gold/player_performance.sql`
- Modify: `transform/models/gold/_gold.yml`

**Interfaces:**
- Consumes: `ref('players')` (silver), `ref('teams')` (silver),
  `ref('stg_statbunker__player_stats')`, `ref('stg_understat__player_stats')`.
- Produces: table `gold.player_performance`, 1 row per `player_id`, columns
  `player_id, player_name, team_id, team_name, league, goals, assists, apps,
  minutes, xg, xa, xg90, xa90`.

- [ ] **Step 1: Write the model**

```sql
{{ config(materialized='table') }}

with statbunker_ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_statbunker__player_stats') }}
    where player_id is not null
),

statbunker_latest as (
    select * from statbunker_ranked where rn = 1
),

understat_ranked as (
    select
        *,
        row_number() over (
            partition by player_id
            order by ingestion_time desc
        ) as rn
    from {{ ref('stg_understat__player_stats') }}
    where player_id is not null
),

understat_latest as (
    select * from understat_ranked where rn = 1
)

select
    p.player_id,
    p.player_name,
    p.team_id,
    t.team_name,
    p.league,
    sb.goals,
    us.assists,
    us.apps,
    us.minutes,
    us.xg,
    us.xa,
    us.xg90,
    us.xa90
from {{ ref('players') }} p
left join {{ ref('teams') }} t
    on t.team_id = p.team_id
left join statbunker_latest sb
    on sb.player_id = p.player_id
left join understat_latest us
    on us.player_id = p.player_id
```

Save as `transform/models/gold/player_performance.sql`. `goals` comes from
statbunker; `assists`/`apps`/`minutes`/`xg`/`xa`/`xg90`/`xa90` come from
understat — understat's own `goals` column (present in staging) is
deliberately not surfaced here, to avoid two disagreeing goal counts in one
row (see spec's "Out of scope").

- [ ] **Step 2: Add schema entry**

Add to `transform/models/gold/_gold.yml`, after the `player_profile` entry:

```yaml
  - name: player_performance
    description: "Player stats: goals (statbunker) + assists/apps/minutes/xG/xA (understat), joined
                  onto identity from silver.players. Grain is 1 row/player_id. Logic: left join
                  silver.players (base) to latest-snapshot-deduped stg_statbunker__player_stats and
                  stg_understat__player_stats on player_id (row_number by ingestion_time desc, same
                  dedup pattern as gold.league_standings's understat join). Stat columns are NULL
                  when a player has no data from that source yet, or when name-matching couldn't
                  resolve player_id — see assert_player_names_mapped and docs/gold_data_contract.md.
                  "
    columns:
      - name: player_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 3: Build and verify**

```bash
dbt build --select player_performance
```

Expected: model builds, `unique`/`not_null` tests on `player_id` pass. Then:

```sql
select * from gold.player_performance
where goals is not null or xg is not null
order by goals desc nulls last
limit 20;
```

Expected: recognizable high-goal Premier League players (e.g. whoever leads
the league this season) appear with plausible `goals`/`xg`/`xa` and correct
`team_name`. Players with no statbunker/understat match show `NULL` stats,
not zeros or errors.

- [ ] **Step 4: Commit**

```bash
git add transform/models/gold/player_performance.sql transform/models/gold/_gold.yml
git commit -m "feat: add gold.player_performance model"
```

---

### Task 9: Update the gold data contract

**Files:**
- Modify: `docs/gold_data_contract.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Add the `gold.player_performance` section**

Insert a new section into `docs/gold_data_contract.md`, immediately after the
`## gold.player_profile` section (after its "Known limitations" bullet list,
before the `---` that precedes `## Out of scope`):

```markdown
---

## gold.player_performance

**Purpose**: Player stats — goals, assists, minutes, xG/xA — for the
`/api/players/{id}/performance` frontend page and chatbot questions like
"how many goals has player X scored" or "what's player X's xG."

**Grain**: 1 row per `player_id`. Enforced by `unique`/`not_null` tests on
`player_id` in `transform/models/gold/_gold.yml` (same pattern as
`player_profile` — no separate `assert_*_unique_grain.sql` needed).

**Freshness**: `materialized='table'` — reflects the most recent statbunker
and understat crawls as of the last `dbt build`, each deduped to its latest
snapshot per player (same "latest wins" pattern as `gold.league_standings`'s
Understat join). Base identity (`player_id`, `player_name`, `team_id`) comes
from `gold.player_profile`'s same source (`silver.players`), so it inherits
that table's Premier-League-only, current-squad-only limitations (see
`gold.player_profile` above).

| Column | Type | Meaning | Nullable? |
|---|---|---|---|
| `player_id` | int | Player identifier from football_data_org | No |
| `player_name` | text | Full player name | No |
| `team_id` | int | Team identifier, anchored on football_data_org | No |
| `team_name` | text | Full team name, from `silver.teams` | Yes |
| `league` | text | Competition slug the team currently plays in | No |
| `goals` | int | Season goals (statbunker) | **Yes** — null if this player couldn't be matched to a statbunker row (see below) |
| `assists` | int | Season assists (understat) | **Yes** — same condition as `xg` |
| `apps` | int | Appearances (understat) | **Yes** — same condition as `xg` |
| `minutes` | int | Minutes played (understat) | **Yes** — same condition as `xg` |
| `xg` | numeric | Expected goals (understat) | **Yes** — null if this player couldn't be matched to an understat row |
| `xa` | numeric | Expected assists (understat) | **Yes** — same condition as `xg` |
| `xg90` | numeric | Expected goals per 90 minutes (understat) | **Yes** — same condition as `xg` |
| `xa90` | numeric | Expected assists per 90 minutes (understat) | **Yes** — same condition as `xg` |

**Known limitations**:

- **Name matching can miss, especially right after a transfer window.**
  statbunker and understat identify players by name only (no shared numeric
  id with football_data_org). Matching normalizes case/accents/punctuation
  (`normalize_player_name`) and falls back to a manually-curated exception
  seed (`transform/seeds/player_name_map.csv`) for names normalization can't
  reconcile (nicknames, large transliteration differences). A miss shows up
  as `NULL` stats for that player — not an error — and as a `warn`-severity
  row in `assert_player_names_mapped`. Unlike `team_name_map.csv` (a
  complete manual roster for ~20 stable teams), `player_name_map.csv` is
  reactive and partial by design — ~600+ players across two sources change
  every transfer window, so it's updated as gaps are found, not upfront.
- **Understat mid-season transfers are unmapped, not misattributed.** When
  understat shows a comma-joined team string for a transferred player (e.g.
  `"Bournemouth, Manchester City"`), that row's `team_id`/`player_id`
  intentionally resolve to `NULL` rather than guessing which team is
  current — the player's stats are missing (not wrong) until the seed or a
  future understat page format resolves it.
- **statbunker only covers Premier League.** `crawlers/statbunker/scraper.py`'s
  `COMPETITION_IDS` has one entry (`PL_2025-2026`) — same existing scope
  limit as `stg_statbunker__standings`. `goals` will always be `NULL` for any
  player outside that scope (moot in practice today, since `silver.players`
  itself is already Premier-League-only — see `gold.player_profile`).

---
```

- [ ] **Step 2: Update the "Out of scope" section**

Replace:

```markdown
## Out of scope

`gold_top_scorers`, `gold_head_to_head`, `gold_player_performance_summary`, and
`gold_match_events_enriched` do not exist yet. `gold.player_profile` (identity
only, Premier League) now exists, but player *stats* (goals, xG/xA) require a
separate crawler + seed-mapping effort (statbunker top scorers, understat
player xG) — tracked as a follow-up sub-project, not built here. Match-event-
level data also has no crawler yet.
```

with:

```markdown
## Out of scope

`gold_head_to_head` and `gold_match_events_enriched` do not exist yet.
Player-level data is now covered end-to-end by `gold.player_profile`
(identity) and `gold.player_performance` (goals/assists/xG/xA), both
Premier-League-only (see their known limitations above). Match-event-level
data still has no crawler.
```

- [ ] **Step 3: Commit**

```bash
git add docs/gold_data_contract.md
git commit -m "docs: document gold.player_performance in the gold data contract"
```

---

### Task 10: Full-system verification and seed backfill

**Files:**
- Modify: `transform/seeds/player_name_map.csv` (only if Step 3 finds real gaps)

**Interfaces:** None (verification + reactive data fix).

- [ ] **Step 1: Full crawl → ingest → build, from a clean slate**

```bash
python crawlers/statbunker/scraper.py
python crawlers/understat/scraper.py
python ingestion/ingest.py
```

From `transform/`:

```bash
dbt build
```

Expected: every model builds, every `error`-severity test passes, and any
`assert_player_names_mapped` warnings are visible in the output (not
blocking).

- [ ] **Step 2: Review unmatched names**

```sql
select source, raw_player_name
from (
    select 'statbunker' as source, raw_player_name, player_id
    from silver.stg_statbunker__player_stats

    union all

    select 'understat' as source, raw_player_name, player_id
    from silver.stg_understat__player_stats
) unmapped_check
where player_id is null
order by source, raw_player_name;
```

For each row, look up the player's actual `football_data_org` name and
`team_id` (e.g. `select player_id, player_name, team_id from
silver.players where player_name ilike '%<partial name>%'`) to confirm
whether it's a genuine spelling mismatch (add to the seed) or an
understat multi-team transfer row (expected — leave it, per the documented
limitation).

- [ ] **Step 3: Backfill genuine mismatches into the seed**

For each confirmed genuine mismatch, append a row to
`transform/seeds/player_name_map.csv`:

```csv
source,raw_player_name,team_id,player_id
statbunker,<exact raw name from the query above>,<team_id>,<player_id>
```

Then reload and rebuild:

```bash
dbt seed --select player_name_map
dbt build --select stg_statbunker__player_stats+ stg_understat__player_stats+
```

Expected: the warning count from `assert_player_names_mapped` drops by
exactly the number of rows added.

- [ ] **Step 4: Spot-check the final gold table**

```sql
select player_name, team_name, goals, assists, xg, xa
from gold.player_performance
where goals is not null
order by goals desc
limit 10;
```

Sanity-check this against publicly known Premier League top scorers for the
current season — values should be in the right ballpark (exact figures may
lag slightly behind the live season if the last crawl wasn't today).

- [ ] **Step 5: Commit (only if the seed changed)**

```bash
git add transform/seeds/player_name_map.csv
git commit -m "fix: backfill player_name_map exceptions found during verification"
```
