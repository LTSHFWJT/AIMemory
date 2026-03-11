ADDITIONAL_COLUMNS: dict[str, dict[str, str]] = {
    "sessions": {
        "owner_agent_id": "TEXT",
        "interaction_type": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
    },
    "conversation_turns": {
        "speaker_participant_id": "TEXT",
        "target_participant_id": "TEXT",
        "turn_type": "TEXT",
        "salience_score": "REAL",
    },
    "working_memory_snapshots": {
        "owner_agent_id": "TEXT",
        "interaction_type": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
        "constraints": "TEXT",
        "resolved_items": "TEXT",
        "unresolved_items": "TEXT",
        "next_actions": "TEXT",
        "budget_tokens": "INTEGER",
        "salience_vector": "TEXT",
        "compression_revision": "INTEGER NOT NULL DEFAULT 1",
    },
    "runs": {
        "owner_agent_id": "TEXT",
        "interaction_type": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
    },
    "memories": {
        "owner_agent_id": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
        "interaction_type": "TEXT",
        "source_session_id": "TEXT",
        "source_run_id": "TEXT",
    },
    "documents": {
        "owner_agent_id": "TEXT",
        "kb_namespace": "TEXT",
        "source_subject_type": "TEXT",
        "source_subject_id": "TEXT",
        "retrieval_count": "INTEGER NOT NULL DEFAULT 0",
        "last_retrieved_at": "TEXT",
        "credibility_score": "REAL NOT NULL DEFAULT 0.5",
    },
    "skills": {
        "owner_agent_id": "TEXT",
        "source_subject_type": "TEXT",
        "source_subject_id": "TEXT",
        "usage_count": "INTEGER NOT NULL DEFAULT 0",
        "last_used_at": "TEXT",
        "success_score": "REAL NOT NULL DEFAULT 0.5",
        "capability_tags": "TEXT",
        "tool_affinity": "TEXT",
    },
    "archive_units": {
        "owner_agent_id": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
        "interaction_type": "TEXT",
        "source_type": "TEXT",
        "restore_pointer": "TEXT",
        "retention_tier": "TEXT",
        "rehydrate_cost": "REAL",
        "last_rehydrated_at": "TEXT",
    },
    "memory_index": {
        "owner_agent_id": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
        "interaction_type": "TEXT",
    },
    "knowledge_chunk_index": {
        "owner_agent_id": "TEXT",
        "source_subject_type": "TEXT",
        "source_subject_id": "TEXT",
    },
    "skill_index": {
        "owner_agent_id": "TEXT",
        "source_subject_type": "TEXT",
        "source_subject_id": "TEXT",
    },
    "archive_summary_index": {
        "owner_agent_id": "TEXT",
        "subject_type": "TEXT",
        "subject_id": "TEXT",
        "interaction_type": "TEXT",
        "source_type": "TEXT",
    },
}

EXTRA_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS participants (
        id TEXT PRIMARY KEY,
        participant_type TEXT NOT NULL,
        external_id TEXT NOT NULL,
        display_name TEXT,
        metadata TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(participant_type, external_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_participants (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        participant_id TEXT NOT NULL,
        participant_role TEXT NOT NULL,
        joined_at TEXT NOT NULL,
        metadata TEXT,
        UNIQUE(session_id, participant_id)
    )
    """,
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
]

POST_MIGRATION_SCHEMA_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_participants_lookup ON participants(participant_type, external_id)",
    "CREATE INDEX IF NOT EXISTS idx_session_participants_session ON session_participants(session_id, joined_at)",
    "CREATE INDEX IF NOT EXISTS idx_semantic_index_domain ON semantic_index_cache(domain, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_semantic_index_collection ON semantic_index_cache(collection, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_owner_subject ON sessions(owner_agent_id, subject_type, subject_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_turns_speaker ON conversation_turns(session_id, speaker_participant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_memories_owner_subject ON memories(owner_agent_id, subject_type, subject_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_agent_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_skills_owner ON skills(owner_agent_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_archive_owner ON archive_units(owner_agent_id, subject_type, subject_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_memory_index_owner ON memory_index(owner_agent_id, subject_type, subject_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_knowledge_index_owner ON knowledge_chunk_index(owner_agent_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_skill_index_owner ON skill_index(owner_agent_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_archive_index_owner ON archive_summary_index(owner_agent_id, subject_type, subject_id, updated_at)",
]
