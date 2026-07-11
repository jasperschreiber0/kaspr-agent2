-- Backfills schema for kaspr-agent2 ("Trend Scout") that has existed in
-- production but was never checked into version control. Idempotent —
-- safe to re-run.

-- ─── Trend briefs ───────────────────────────────────────────────────────────
-- Written by: agent2 (src/brief_writer.py)
-- Read by:    agent3 (src/supabase.js getLatestTrendBrief)

create table if not exists trend_briefs (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references clients(id) on delete set null,
  niche text not null,
  content_angles text[] not null default array[]::text[],
  trending_audio text[] not null default array[]::text[],
  hashtags text[] not null default array[]::text[],
  competitor_note text,
  raw_brief text,
  used_at timestamptz, -- set by agent3 once a post is scheduled from this brief
  created_at timestamptz not null default now()
);

create index if not exists trend_briefs_client_id_idx on trend_briefs(client_id);
-- Matches agent2's get_previous_brief() and agent3's getLatestTrendBrief(),
-- both of which order by created_at desc and take the top row per client.
create index if not exists trend_briefs_client_created_idx
  on trend_briefs(client_id, created_at desc);

-- ─── OpenClaw event bus ─────────────────────────────────────────────────────
-- NOTE: despite this module's docstring describing Supabase Realtime,
-- every consumer (agent2's poll_openclaw_events, agent3's pollEvents)
-- does plain REST polling, not a Realtime subscription. This table backs
-- a poll-based queue, not a push-based event bus, as currently built.
--
-- Written by: agent2 (src/openclaw.py emit), agent3 (src/openclaw.js emit).
--             agent1 does NOT write here — it has no OpenClaw integration
--             at all, even though agent3 listens for a 'content.received'
--             event documented as coming from it. That event is never
--             actually emitted anywhere in the audited system.
-- Read by:    agent2 (poll_openclaw_events, daemon mode only),
--             agent3 (pollEvents, every 30s tick)

create table if not exists openclaw_events (
  id uuid primary key default gen_random_uuid(),
  event_name text not null,
  source text not null,
  payload jsonb not null default '{}'::jsonb,
  processed boolean not null default false,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

-- Matches both agents' poll queries: filter by event_name (or IN-list),
-- processed = false, order by created_at asc.
create index if not exists openclaw_events_name_processed_idx
  on openclaw_events(event_name, processed, created_at);

-- ─── OpenClaw agent health/status ───────────────────────────────────────────
-- Written by: agent2 (log_soul_status), agent3 (logStatus) — upserted via
--             Prefer: resolution=merge-duplicates, one row per agent.
-- Read by:    nothing in the audited repos today. Write-only from
--             kaspr-site/agent1/agent2/agent3's perspective — if no
--             external "OpenClaw dashboard" reads this, it's dead weight.

create table if not exists openclaw_agent_status (
  agent text primary key,
  status text not null, -- 'running' | 'idle' | 'error' | 'complete'
  detail text,
  updated_at timestamptz not null default now()
);
