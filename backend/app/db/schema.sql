-- LinkedIn-First Personal CRM Database Schema
-- PostgreSQL 14+

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enums
CREATE TYPE person_origin AS ENUM ('linkedin', 'manual', 'promoted', 'email_only');
CREATE TYPE interaction_kind AS ENUM ('email_in', 'email_out', 'meeting', 'linkedin_connect', 'note');
CREATE TYPE interaction_channel AS ENUM ('imap', 'ost', 'calendar', 'linkedin', 'manual');

-- People table: Core contact records
CREATE TABLE people (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name TEXT NOT NULL,
    primary_email CITEXT,
    linkedin_url TEXT,
    linkedin_id TEXT,
    company TEXT,
    title TEXT,
    tags TEXT[] DEFAULT '{}',
    origin person_origin NOT NULL DEFAULT 'email_only',
    is_tracked BOOLEAN NOT NULL DEFAULT FALSE,
    linkedin_connected_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Person emails: Multiple emails per person (for matching)
CREATE TABLE person_emails (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    email CITEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT, -- 'linkedin', 'imap', 'manual'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Calendar series: Recurring meeting definitions
CREATE TABLE calendar_series (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_series_id TEXT NOT NULL,
    organizer_email CITEXT,
    subject TEXT,
    timezone TEXT DEFAULT 'UTC',
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    rrule TEXT,
    recurrence_blob JSONB,
    source_account TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source_series_id, source_account)
);

-- Calendar occurrences: Individual meeting instances
CREATE TABLE calendar_occurrences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    series_id UUID REFERENCES calendar_series(id) ON DELETE SET NULL,
    external_id TEXT NOT NULL,
    subject TEXT,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ,
    timezone TEXT,
    location TEXT,
    organizer_email CITEXT,
    participants JSONB DEFAULT '[]',
    is_exception BOOLEAN NOT NULL DEFAULT FALSE,
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    is_all_day BOOLEAN NOT NULL DEFAULT FALSE,
    source_account TEXT,
    raw_ref JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(external_id, source_account)
);

-- Interactions: All contact touchpoints (email, meetings, notes)
CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    kind interaction_kind NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ,
    direction TEXT, -- 'inbound', 'outbound', NULL for meetings
    channel interaction_channel NOT NULL,
    subject TEXT,
    snippet TEXT,
    participants JSONB DEFAULT '[]',
    external_id TEXT,
    source_account TEXT,
    raw_ref JSONB,
    -- Derived flags for filtering
    is_automated BOOLEAN DEFAULT FALSE,
    is_bulk BOOLEAN DEFAULT FALSE,
    is_meaningful BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Person scores: Cached connection strength metrics
CREATE TABLE person_scores (
    person_id UUID PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    score_total INTEGER NOT NULL DEFAULT 0,
    score_breakdown JSONB NOT NULL DEFAULT '{}',
    interaction_count INTEGER DEFAULT 0,
    last_interaction_at TIMESTAMPTZ,
    last_inbound_at TIMESTAMPTZ,
    last_outbound_at TIMESTAMPTZ,
    last_meeting_at TIMESTAMPTZ,
    next_meeting_at TIMESTAMPTZ,
    first_interaction_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ingestion checkpoints: Track progress for incremental imports
CREATE TABLE ingestion_checkpoints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source TEXT NOT NULL, -- 'imap', 'ost_calendar', 'ost_email'
    account TEXT NOT NULL,
    folder TEXT,
    checkpoint_data JSONB NOT NULL DEFAULT '{}', -- Flexible: last_date, last_id, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, account, folder)
);

-- Unlinked review queue: Pending matches and promotions
CREATE TABLE review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    queue_type TEXT NOT NULL, -- 'promote', 'link_suggestion'
    suggested_person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    confidence_score FLOAT,
    match_reason JSONB,
    interaction_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'accepted', 'rejected', 'ignored'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

-- User settings (single user for v1)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auth tokens (simple session management)
CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_people_is_tracked ON people(is_tracked) WHERE is_tracked = TRUE;
CREATE INDEX idx_people_origin ON people(origin);
CREATE INDEX idx_people_full_name_trgm ON people USING gin(full_name gin_trgm_ops);
CREATE INDEX idx_people_company_trgm ON people USING gin(company gin_trgm_ops);

CREATE UNIQUE INDEX idx_person_emails_email ON person_emails(email);
CREATE INDEX idx_person_emails_person_id ON person_emails(person_id);

CREATE INDEX idx_interactions_person_occurred ON interactions(person_id, occurred_at DESC);
CREATE UNIQUE INDEX idx_interactions_external_channel ON interactions(external_id, channel) WHERE external_id IS NOT NULL;
CREATE INDEX idx_interactions_occurred_at ON interactions(occurred_at DESC);
CREATE INDEX idx_interactions_meaningful ON interactions(person_id, occurred_at DESC) WHERE is_meaningful = TRUE;

CREATE INDEX idx_calendar_occurrences_start ON calendar_occurrences(start_at);
CREATE INDEX idx_calendar_occurrences_participants ON calendar_occurrences USING gin(participants);

CREATE INDEX idx_person_scores_total ON person_scores(score_total DESC);
CREATE INDEX idx_person_scores_next_meeting ON person_scores(next_meeting_at) WHERE next_meeting_at IS NOT NULL;

CREATE INDEX idx_review_queue_status ON review_queue(status) WHERE status = 'pending';

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_people_updated_at BEFORE UPDATE ON people FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_calendar_series_updated_at BEFORE UPDATE ON calendar_series FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_calendar_occurrences_updated_at BEFORE UPDATE ON calendar_occurrences FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_person_scores_updated_at BEFORE UPDATE ON person_scores FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_ingestion_checkpoints_updated_at BEFORE UPDATE ON ingestion_checkpoints FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_settings_updated_at BEFORE UPDATE ON settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
