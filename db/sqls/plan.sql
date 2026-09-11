-- Existing databases: execute this file to add the two tables.
-- Enable foreign_keys on each connection for raw SQL cascading deletes.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chat(id),
    trace_id TEXT,
    user_input TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'cancelled')),
    result JSON CHECK (result IS NULL OR json_valid(result)),
    error TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_plan_chat ON plan(chat_id, id);
CREATE INDEX IF NOT EXISTS idx_plan_trace ON plan(trace_id);

CREATE TABLE IF NOT EXISTS plan_step (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
    step_seq INTEGER NOT NULL CHECK (step_seq > 0),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped', 'cancelled')),
    result JSON CHECK (result IS NULL OR json_valid(result)),
    error TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (plan_id, step_seq)
);
