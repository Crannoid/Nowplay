-- Normalized watchlist schema. One row per title-per-platform, optionally
-- enriched with third-party metadata (poster/overview) via TMDB.
-- Common across all platforms this project will ever scrape, even though
-- only Netflix/Disney+/BBC iPlayer/HBO Max/Prime Video are implemented so far.

-- Metadata is a separate table, not columns on watchlist_items, because the
-- same film can sit on two platforms' watchlists at once (two rows in
-- watchlist_items) and should share one TMDB lookup/poster/overview rather
-- than fetching and storing it twice. Keyed on TMDB's own id so a second
-- platform's match reuses the existing row instead of duplicating it — see
-- db.get_or_create_title_metadata(). Decided 2026-08-05, see Data Model in
-- Notion for the full reasoning (including the flat-columns alternative,
-- which was also defensible at this project's scale).
CREATE TABLE IF NOT EXISTS title_metadata (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_id          INTEGER NOT NULL UNIQUE,   -- dedup key across platforms
    media_type       TEXT NOT NULL,             -- 'movie' | 'tv' (TMDB's own classification)
    title            TEXT NOT NULL,             -- TMDB's canonical title, not the scraped one
    release_year     TEXT,
    poster_url       TEXT,
    overview         TEXT,
    match_confidence TEXT NOT NULL,             -- 'exact' | 'fuzzy' | 'manual'
    fetched_at       TEXT NOT NULL              -- ISO timestamp of this TMDB fetch
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform            TEXT NOT NULL,              -- e.g. 'netflix', 'disney_plus', 'prime_video'
    external_id         TEXT,                       -- platform's own id for the title, if scrapeable
    title               TEXT NOT NULL,
    media_type          TEXT,                       -- 'movie' | 'series' | 'unknown'
    date_added          TEXT,                       -- ISO date, if the platform exposes it; NULL otherwise
    raw_json            TEXT,                       -- raw scraped fields, for debugging/future re-parsing
    first_seen_at       TEXT NOT NULL,              -- ISO timestamp, first time this scraper saw the item
    last_seen_at        TEXT NOT NULL,              -- ISO timestamp, most recent scrape that saw it
    removed_at          TEXT,                       -- ISO timestamp, set when a scrape no longer finds it
    title_metadata_id   INTEGER REFERENCES title_metadata(id) ON DELETE SET NULL,
    metadata_checked_at TEXT,                       -- last enrichment attempt, any outcome incl. no_match —
                                                      -- stops the enrichment step re-querying TMDB every scrape
                                                      -- for a title that's confirmed to have no match
    UNIQUE (platform, title, external_id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_platform ON watchlist_items (platform);
CREATE INDEX IF NOT EXISTS idx_watchlist_removed ON watchlist_items (removed_at);

-- idx_watchlist_metadata is NOT created here — it indexes title_metadata_id,
-- a column that doesn't exist yet on a pre-2026-08-05 watchlist_items table.
-- executescript() runs this whole file in one pass, before db.init_db()'s
-- Python-side migration has a chance to add that column to an old DB, so
-- creating the index here would fail on upgrade. See init_db() in db.py —
-- it creates this index itself, after the migration step runs.
