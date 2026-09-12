-- One current memory snapshot per chat. Topics and facts stay inside memory.
-- last_processed_message_id=0 means no messages processed yet.
-- Update memory and the cursor in one transaction after successful validation.
-- Raw SQL updates must explicitly set updated_at=CURRENT_TIMESTAMP.
-- Enable PRAGMA foreign_keys=ON on each connection for cascading deletes.
CREATE TABLE IF NOT EXISTS chat_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    memory JSON NOT NULL DEFAULT '{"topics":[]}'
        CHECK (json_valid(memory) AND json_type(memory) = 'object'),
    last_processed_message_id INTEGER NOT NULL DEFAULT 0
        CHECK (last_processed_message_id >= 0),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_chat_memory_chat UNIQUE (chat_id),
    FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE
);
