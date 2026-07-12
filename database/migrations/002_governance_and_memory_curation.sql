-- database/migrations/002_governance_and_memory_curation.sql
-- Additive only — nothing in the original 8 tables changes (per v2 Section 7).

CREATE TABLE session_risk_scores (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    running_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    last_verdict  VARCHAR(20) NOT NULL DEFAULT 'allow',   -- allow / flag / block
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TRIGGER trg_session_risk_updated_at
    BEFORE UPDATE ON session_risk_scores
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE identity_tokens (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    scope         JSONB NOT NULL DEFAULT '{}',       -- which tools/resources this run may touch
    tool_call_log JSONB NOT NULL DEFAULT '[]',        -- append-only log of calls made under this token
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_identity_tokens_task ON identity_tokens(task_id);

CREATE TABLE curated_memory (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,  -- memory should outlive the task
    tag            VARCHAR(30) NOT NULL,   -- architectural_decision / known_bug
    summary        TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_curated_memory_project ON curated_memory(project_id);
CREATE INDEX idx_curated_memory_tag ON curated_memory(tag);