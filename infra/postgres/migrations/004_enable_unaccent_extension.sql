-- =========================================================
-- Enable the unaccent extension (used by normalize_player_name macro)
-- Football Data Platform
-- =========================================================
-- Lets dbt models strip accents when matching player names across sources
-- (e.g. statbunker's "Gyokeres" vs a possible accented understat spelling),
-- without maintaining a fully manual name-mapping seed for ~600+ players.

CREATE EXTENSION IF NOT EXISTS unaccent;
