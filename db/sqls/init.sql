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
    content text not null,
    created_at text not null default current_timestamp,
    metadata text 
)