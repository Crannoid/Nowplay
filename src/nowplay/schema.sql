-- Normalized watchlist schema. One row per title-per-platform.
-- Common across all platforms this project will ever scrape, even though
-- only Netflix is implemented right now.

CREATE TABLE IF NOT EXISTS watchlist_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,              -- e.g. 'netflix', 'disney_plus', 'prime_video'
    external_id   TEXT,                       -- platform's own id for the title, if scrapeable
    title         TEXT NOT NULL,
    media_type    TEXT,                       -- 'movie' | 'series' | 'unknown'
    date_added    TEXT,                       -- ISO date, if the platform exposes it; NULL otherwise
    raw_json      TEXT,                       -- raw scraped fields, for debugging/future re-parsing
    first_seen_at TEXT NOT NULL,              -- ISO timestamp, first time this scraper saw the item
    last_seen_at  TEXT NOT NULL,              -- ISO timestamp, most recent scrape that saw it
    removed_at    TEXT,                       -- ISO timestamp, set when a scrape no longer finds it
    UNIQUE (platform, title, external_id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_platform ON watchlist_items (platform);
CREATE INDEX IF NOT EXISTS idx_watchlist_removed ON watchlist_items (removed_at);
