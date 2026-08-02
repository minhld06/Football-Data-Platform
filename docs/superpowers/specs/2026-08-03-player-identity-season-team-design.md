# Player Identity & Season-Scoped Team Resolution

Date: 2026-08-03

## Context

Triggered by the user noticing Mohamed Salah missing from Liverpool's squad/top
scorer page. Investigation (this session, not guessed) found two distinct,
related gaps in the existing player-level data built by
[`2026-07-24-player-identity-design.md`](2026-07-24-player-identity-design.md)
and [`2026-07-25-player-stats-design.md`](2026-07-25-player-stats-design.md):

1. **~86 players with real 2025-26 statbunker/understat stats have zero
   football_data_org row at all** (Salah, Casemiro, Bernardo Silva, Douglas
   Luiz, etc.), so `silver.players`/`gold.player_profile` — anchored entirely
   on football_data_org's numeric `player_id` — has no row to attach their
   stats to.
2. **~25 players show an incorrect team** in `gold.player_performance` (e.g.
   Jack Grealish displays as "Manchester City FC" carrying his actual
   Everton-loan stat line: 2 goals / 6 assists / 20 apps / 1645 min).

**Root cause for both, confirmed via crawler source, not assumption**:
`crawlers/football_data_org/client.py` squad endpoint (`/v4/teams/{id}`) has
no `season` param and "always returns the present-day roster" (its own code
comment) — i.e. whatever football_data_org's database says *right now*
(effectively the 2026-27 preseason at the 2026-07-24 crawl date). Meanwhile
`crawlers/understat/scraper.py` and `crawlers/statbunker/scraper.py` explicitly
request season "2025"/"2025-2026" — the season that had already *concluded* by
crawl time (confirmed: max `minutes` value is 3420 = 90×38, a full completed
season). So fdo's squad and statbunker/understat's stats describe **two
different points in time** under the same `season` label
(`ingestion/core/metadata.py`'s `parse_league_season` tags all three the
same way from the filename). Comparing them directly — as
`gold.player_performance` currently does — surfaces every transfer,
retirement, contract expiry, and loan start/end that happened between "last
season ended" and "now" as if it were a data bug. An earlier theory in this
investigation (fdo squad being a stale multi-year cache, based on a
`lastUpdated` field showing 2022–2024 across teams) was **checked and
retracted** — Liverpool's crawled squad includes 2025 summer signings
(Wirtz, Isak, Ekitike), which a stale cache could not contain, so
`lastUpdated` does not indicate squad staleness and should not be reused as a
signal.

**Two further findings from this investigation, folded into this design**:
- **Understat's raw player-stats payload carries its own native numeric
  player `id`** (e.g. `{"id": "8260", "player_name": "Erling Haaland", ...}`),
  currently discarded — `stg_understat__player_stats` has no column for it.
  This id is stable across seasons for the same person and is a much more
  reliable anchor than hashing a normalized name.
- **statbunker contributes no unique identities beyond understat.** Checked
  directly: of 280 statbunker premier-league players, 261 already match an
  understat player by normalized name; the remaining 19 were checked
  individually and are *all* the same person as an existing understat row
  under a different spelling/nickname/transliteration (e.g. "Savinho" vs.
  understat's "Sávio", "Rodri Hernandez" vs. "Rodri") — zero are genuinely
  statbunker-only. statbunker also has no native id and no `minutes` column.
  So it plays no role in identity resolution going forward — it stays a
  supplementary stats source (goal-split columns) joined onto whichever
  identity fdo/understat already established.

## Goal

Squad, top scorer/assist, and player-performance views should reflect **who
was actually on a team during a given season** — including players loaned to
another EPL club (shown under the loan club, not the parent club) — rather
than football_data_org's undated "current roster" snapshot. This must not
regress the existing `/players/{id}` identity anchor for the ~588 players
football_data_org already covers.

## Decisions

### Identity resolution — rewritten `silver/players.sql`

Replaces the football_data_org-only model from the 2026-07-24 spec. Priority
order per person:

1. Has a football_data_org `player_id` → use it unchanged (zero disruption to
   existing `/players/{id}` routes and `PlayerProfile.player_id: int`).
2. No football_data_org row, but resolvable to an understat row → use
   **understat's native id + a fixed offset** (`understat_id + 100000000`) as
   `player_id`. The offset is arbitrary but keeps the two id spaces from ever
   colliding — observed football_data_org ids top out around 270,684, so 100
   million of headroom is a safe, simple margin; it needs no lookup table,
   just a constant added at read time.
3. Dedup fdo ↔ understat before assigning ids: `FULL OUTER JOIN` on
   `normalize_player_name()` (existing macro) so a person present in both
   sources (the common case) gets exactly one id (fdo's, per priority 1), not
   two. Confirmed this catches Salah correctly (`"Mohamed Salah"` normalizes
   identically in both).
4. statbunker generates no id of its own (see Context finding above) — it
   only ever joins onto an id already established by steps 1–3, via the
   existing `player_name_map.csv` + `normalize_player_name()` fallback.
   Residual misses (e.g. the Savinho/Sávio case, which no automated
   normalization catches) are handled the same way unmapped names always are
   — a manual `player_name_map.csv` row, surfaced by
   `assert_player_names_mapped`.
5. Bio fields (`position`, `date_of_birth`, `nationality`, `shirt_number`) —
   come from football_data_org when available (step 1 players). Understat/
   statbunker never carry these, so priority-2 players get `NULL` here unless
   filled via the (not-yet-built, out of scope) `player_extra_info.csv` seed
   floated in prior investigation notes.
6. `team_id` is **no longer part of this model's core identity** — see next
   section. `silver.players` keeps a `team_id` column only as a display
   convenience (see gold section below), not as the source of squad
   membership.

New required column on `stg_understat__player_stats`: raw understat `id`
(currently dropped during parsing) — passed through unchanged so step 2 above
has something to offset.

### Season-scoped team resolution — new `silver/player_team_season.sql`

Grain: one row per `(player_id, season)`. For each combination, `team_id` is
resolved in this order:

1. understat has a row for this player+season → use its `team_id` (richest
   source: has `minutes`, confirms actual game time, already correctly
   attributes loan players to the loan club — confirmed with Grealish/
   Everton).
2. Else, statbunker has a row → use its `team_id`.
3. Else (zero stats rows in either source this season — e.g. an unused
   third-choice keeper, or a long-term injury) → fall back to
   football_data_org's team_id from the rewritten `silver/players.sql`. This
   is the only case where "current roster" is used as a stand-in for
   "season roster," accepted per the user's own choice earlier in this
   design discussion.
4. If understat **and** statbunker both have a row for the same
   player+season but *disagree* on `team_id` (a genuine mid-season transfer
   within one season, distinct from the between-seasons case this whole
   design is about) — understat wins (richer source), and the disagreement
   is surfaced by a new warn-severity test rather than silently resolved (see
   Testing below).

### Gold layer

**`gold/player_profile.sql`** — stays `materialized='view'`, grain unchanged
(one row per `player_id`), stays pure identity/bio. `team_id`/`team_name`
becomes a **convenience field only**: the `player_team_season` row for the
most recent season available for that player (still falls back to fdo's
`team_id` per step 3 above when no season data exists at all). This is
*not* the source of truth for squad membership — it exists so the player
detail page header can show "currently plays for X" without a season param.

**`gold/player_performance.sql`** — grain changes from `player_id` to
`(player_id, season)`. Rebuilt from `player_team_season` (for `team_id`/
`team_name`) left-joined to statbunker/understat stats for that same
`(player_id, season)`, instead of joining everything onto a single
`silver.players.team_id` as it does today.

### Backend (`backend/routers/`)

"Latest season" throughout this section means `max(season)` — the `YYYY-YYYY`
format already in use sorts correctly as a plain string, so no extra parsing
is needed to pick it.

- **`GET /teams/{team_id}/squad`** — query changes: join `gold.player_performance`
  (filtered on `team_id` + `season`, defaulting to the latest season present)
  to `gold.player_profile` (for bio fields), instead of filtering
  `player_profile.team_id` directly. Response model (`list[PlayerProfile]`)
  stays the same shape.
- **`GET /players/{player_id}`** — unchanged (still pure `gold.player_profile`
  lookup by `player_id`).
- **`GET /players/{player_id}/performance`** — add optional `season: str | None`
  query param (same pattern as `GET /teams/{team_id}/matches`), defaulting to
  the latest season if omitted. Still returns one `PlayerPerformance` object.
- **`GET /players/top-scorers`** / **`GET /players/top-assists`** — add the
  same optional `season` param, defaulting to latest.
- `PlayerPerformance` Pydantic schema gains a `season: str` field
  (non-nullable — grain requires it).

### Testing

- `unique`/`not_null` on `silver.players.player_id` (unchanged expectation,
  now covering both id spaces).
- New `assert_player_team_season_unique_grain.sql` — one row per
  `(player_id, season)` in `silver.player_team_season`.
- New `assert_gold_player_performance_unique_grain.sql` — one row per
  `(player_id, season)` in `gold.player_performance` (grain changed from the
  single-column test the 2026-07-25 spec used).
- New warn-severity `assert_player_team_season_source_agreement.sql` —
  surfaces player+season rows where statbunker and understat both report a
  `team_id` and disagree (case 4 above). Warn, not error, because a genuine
  mid-season transfer is expected behavior, not a bug — the test exists so
  it's visible, not so it blocks `dbt build`.
- Existing `assert_player_names_mapped` (warn) keeps its role for
  statbunker/understat names that fail to resolve to any `player_id`.

### Known limitations (to document in `docs/gold_data_contract.md`)

- **`gold.player_profile.team_id` is a convenience "latest known team," not a
  season-scoped fact.** For "who was on team X in season Y," callers must go
  through `gold.player_performance` (or `/teams/{id}/squad?season=Y`), never
  `player_profile.team_id` — documenting this prevents a future consumer from
  reintroducing the exact bug this design fixes.
- **Priority-2 players (understat-anchored, no fdo row) have no bio fields**
  until/unless a manual seed (`player_extra_info.csv`, previously discussed,
  not built here) is added — `position`/`date_of_birth`/`nationality`/
  `shirt_number` are `NULL` for them, consistent with the existing "silently
  null downstream, not an error" contract already used for
  `xg`/`xga`/`shirt_number` elsewhere in the gold contract.
- **understat's mid-season-transfer rows already resolve to `NULL` `team_id`**
  (comma-joined team string, decided in the 2026-07-25 spec) — unchanged by
  this design; those rows simply don't participate in `player_team_season`
  resolution for that season (falls through to statbunker, then fdo, per the
  priority order above).
- **The 100,000,000 offset for understat-anchored ids is an assumption, not a
  guarantee**, should football_data_org ever assign an id that large (not
  observed in current data, where the max is ~270,684).

## Testing plan

1. Add the raw understat `id` field to `stg_understat__player_stats.sql`.
2. Rewrite `silver/players.sql` per the identity-resolution decisions; add
   `silver/player_team_season.sql`.
3. Update `gold/player_profile.sql` and `gold/player_performance.sql`.
4. `dbt build` — confirm new grain tests pass, note (not necessarily fix
   immediately) any `assert_player_names_mapped` /
   `assert_player_team_season_source_agreement` warnings.
5. Spot-check: `select * from gold.player_profile where player_name ilike
   '%salah%'` returns a row (previously zero rows). `select * from
   gold.player_performance where player_name ilike '%grealish%'` shows
   `team_name = 'Everton FC'` for season 2025-2026 (previously
   'Manchester City FC').
6. Update backend routers/schemas per the Backend section; add `season`
   query param tests (default vs. explicit) for the 4 endpoints listed.
7. Manually verify `/teams/{everton_id}/squad?season=2025-2026` includes
   Grealish and `/teams/{man_city_id}/squad?season=2025-2026` does not.
8. Update `docs/gold_data_contract.md` with the known limitations above.

## Out of scope

- `player_extra_info.csv` seed for understat-anchored players' bio fields —
  referenced as a future step, not built in this design.
- SCD2 history / full season-over-season squad browsing UI — this design
  makes `gold.player_performance` correctly season-scoped so that capability
  *can* be built later without rework, but no frontend season-selector work
  is included here.
- Ligue 1 — statbunker doesn't cover it today (per the 2026-07-25 spec); no
  change to that scope here.
- Re-litigating the retracted `lastUpdated`-staleness theory — recorded in
  memory as a dead end, not revisited here.
