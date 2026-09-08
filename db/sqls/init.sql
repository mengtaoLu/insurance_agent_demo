create table if not exists user (
    id integer not null 
        constraint user_id_pk 
            primary key autoincrement,
    username text not null,
    email text,
    password_hash text not null default 'a',
    status integer not null default 1,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists auth_session (
    id integer not null
        constraint auth_session_id_pk
            primary key autoincrement,
    user_id integer not null
        constraint auth_session_user_id_fk
            references user(id),
    token_hash text not null,
    created_at text not null default current_timestamp,
    expires_at text not null,
    revoked_at text 
);

create table if not exists chat (
    id integer not null
        constraint chat_id_pk
            primary key autoincrement,
    user_id integer not null
        constraint chat_user_id_fk
            references user(id),
    title text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create table if not exists messages (
    id integer not null
        constraint messages_id_pk
            primary key autoincrement,
    chat_id integer not null
        constraint messages_chat_id_fk
            references chat(id),
    role text not null,
    content text,
    created_at text not null default current_timestamp,
    metadata text
);

CREATE TABLE IF NOT EXISTS trace_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id        TEXT NOT NULL,
    chat_id         INTEGER NOT NULL,

    turn_no         INTEGER NOT NULL,
    step_no         INTEGER NOT NULL,
    sequence_no     INTEGER NOT NULL,

    event_type      TEXT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('pending', 'running', 'success', 'fail')),

    role            TEXT
                    CHECK (
                        role IS NULL OR
                        role IN ('system', 'user', 'assistant', 'tool')
                    ),

    name            TEXT,
    content         TEXT,
    usage           TEXT CHECK (usage IS NULL OR json_valid(usage)),
    finish_reason   TEXT,
    error           TEXT,
    metadata        TEXT CHECK (metadata IS NULL OR json_valid(metadata)),

    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     TEXT,

    FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE,
    UNIQUE (trace_id, sequence_no),

    CHECK (turn_no >= 0),
    CHECK (step_no >= 0),
    CHECK (sequence_no >= 0)
);

CREATE INDEX IF NOT EXISTS idx_trace_event_trace
ON trace_event(trace_id, sequence_no);

CREATE INDEX IF NOT EXISTS idx_trace_event_chat
ON trace_event(chat_id, created_at);
