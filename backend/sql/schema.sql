-- OpenCleaner AI — local SQLite schema (example / production)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS allowlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern TEXT NOT NULL,
  pattern_type TEXT NOT NULL CHECK (pattern_type IN ('process', 'service', 'path_prefix', 'hash')),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS blocklist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern TEXT NOT NULL,
  pattern_type TEXT NOT NULL CHECK (pattern_type IN ('process', 'service', 'path_prefix')),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scans (
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  summary_json TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS scan_items (
  id TEXT PRIMARY KEY,
  scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  item_type TEXT NOT NULL,
  name TEXT NOT NULL,
  path TEXT,
  detail_json TEXT NOT NULL,
  rule_bucket TEXT NOT NULL,
  ml_score REAL,
  confidence REAL NOT NULL,
  reasoning TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scan_items_scan ON scan_items(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_items_type ON scan_items(item_type);
CREATE INDEX IF NOT EXISTS idx_scan_items_bucket ON scan_items(rule_bucket);

CREATE TABLE IF NOT EXISTS quarantine_entries (
  id TEXT PRIMARY KEY,
  original_path TEXT NOT NULL,
  quarantine_path TEXT NOT NULL,
  hash_sha256 TEXT,
  size_bytes INTEGER,
  meta_json TEXT NOT NULL,
  restored INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  mode TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT 'local_ui',
  detail_json TEXT NOT NULL,
  success INTEGER NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

CREATE TABLE IF NOT EXISTS user_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_fingerprint TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('keep', 'remove', 'ignore')),
  weight REAL NOT NULL DEFAULT 1.0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feedback_fingerprint ON user_feedback(item_fingerprint);

CREATE TABLE IF NOT EXISTS ml_model_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  trained_at TEXT NOT NULL,
  feature_version INTEGER NOT NULL,
  notes TEXT
);
