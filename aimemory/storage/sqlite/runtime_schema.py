EXTRA_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS semantic_index_cache (
        record_id TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        collection TEXT NOT NULL,
        text TEXT NOT NULL,
        embedding TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        quality REAL NOT NULL DEFAULT 0.0,
        updated_at TEXT NOT NULL,
        metadata TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_semantic_index_domain ON semantic_index_cache(domain, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_semantic_index_collection ON semantic_index_cache(collection, updated_at)",
]
