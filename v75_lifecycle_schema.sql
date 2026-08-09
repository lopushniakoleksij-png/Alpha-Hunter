create table if not exists alpha_hunter_lifecycle_episodes (
    episode_id text primary key,

    symbol text not null,
    path text not null,

    first_detected_at_utc timestamptz not null,
    last_detected_at_utc timestamptz not null,

    first_detection_price double precision,
    latest_price double precision,

    detections integer not null default 1,

    lifecycle_state text not null,
    previous_state text,

    v74_score double precision,
    v74_rank integer,
    v74_tier text,

    v741_shadow_score double precision,
    v741_shadow_rank integer,

    direction text,

    trade_permission boolean not null default false,
    v7_trade_ready boolean not null default false,

    max_favorable_excursion_pct double precision not null default 0,
    max_adverse_excursion_pct double precision not null default 0,

    expansion_3_hit boolean not null default false,
    expansion_5_hit boolean not null default false,
    expansion_10_hit boolean not null default false,

    first_3pct_at_utc timestamptz,
    first_5pct_at_utc timestamptz,
    first_10pct_at_utc timestamptz,

    final_classification text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists
idx_alpha_hunter_lifecycle_symbol
on alpha_hunter_lifecycle_episodes(symbol);

create index if not exists
idx_alpha_hunter_lifecycle_state
on alpha_hunter_lifecycle_episodes(lifecycle_state);

create index if not exists
idx_alpha_hunter_lifecycle_path
on alpha_hunter_lifecycle_episodes(path);

create index if not exists
idx_alpha_hunter_lifecycle_first_detected
on alpha_hunter_lifecycle_episodes(first_detected_at_utc desc);

create index if not exists
idx_alpha_hunter_lifecycle_last_detected
on alpha_hunter_lifecycle_episodes(last_detected_at_utc desc);
