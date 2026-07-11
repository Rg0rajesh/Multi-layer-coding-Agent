-- database/schema.sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Reused by every table with an updated_at column
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    display_name    VARCHAR(100),
    password_hash   VARCHAR(255),               -- null for OAuth-only accounts
    avatar_url      TEXT,
    bio             TEXT,
    website_url     TEXT,
    github_url      TEXT,
    twitter_handle  VARCHAR(50),
    plan            VARCHAR(20) DEFAULT 'free',
    role            VARCHAR(20) DEFAULT 'user',
    github_id       VARCHAR(100),
    google_id       VARCHAR(100),
    is_active       BOOLEAN DEFAULT true,
    is_verified     BOOLEAN DEFAULT false,
    two_fa_enabled  BOOLEAN DEFAULT false,
    two_fa_secret   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE teams (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 VARCHAR(255) NOT NULL,
    logo_url             TEXT,
    subdomain            VARCHAR(100) UNIQUE,
    owner_id             UUID NOT NULL REFERENCES users(id),
    shared_api_key       VARCHAR(255),
    default_agent_config JSONB DEFAULT '{}',
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE team_members (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id   UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role      VARCHAR(20) DEFAULT 'viewer',   -- owner / admin / editor / viewer
    status    VARCHAR(20) DEFAULT 'active',   -- active / invited / suspended
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (team_id, user_id)
);
CREATE INDEX idx_team_members_user ON team_members(user_id);

CREATE TABLE projects (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id      UUID REFERENCES teams(id),
    name         VARCHAR(255) NOT NULL,
    description  TEXT,
    stack_badges JSONB DEFAULT '[]',
    status       VARCHAR(30) DEFAULT 'active',    -- active / completed / archived
    visibility   VARCHAR(20) DEFAULT 'private',   -- private / team / public
    git_repo_url TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_projects_user ON projects(user_id);
CREATE INDEX idx_projects_team ON projects(team_id);
CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE tasks (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id           UUID REFERENCES projects(id),
    title                VARCHAR(500) NOT NULL,
    description          TEXT,
    language             VARCHAR(50),
    framework            VARCHAR(100),
    project_type         VARCHAR(50),
    priority             VARCHAR(20) DEFAULT 'medium',
    status               VARCHAR(30) DEFAULT 'pending',
    coordination_pattern VARCHAR(30) DEFAULT 'sequential',
    max_exec_minutes     INTEGER DEFAULT 10,
    output_format        VARCHAR(30) DEFAULT 'commented',
    git_integration      BOOLEAN DEFAULT false,
    agents_config        JSONB DEFAULT '{}',
    context_files        JSONB DEFAULT '[]',
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    elapsed_seconds      INTEGER DEFAULT 0,
    -- workflow-centric metrics (C5)
    replan_count         INTEGER DEFAULT 0,
    coder_retries        INTEGER DEFAULT 0,
    safety_issues_found  INTEGER DEFAULT 0,
    human_interventions  INTEGER DEFAULT 0,
    total_lines_written  INTEGER DEFAULT 0,
    test_count           INTEGER DEFAULT 0,
    tests_passed         INTEGER DEFAULT 0,
    review_score         DECIMAL(4,2),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tasks_user_id ON tasks(user_id);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_name      VARCHAR(50) NOT NULL,
    agent_color     VARCHAR(10),
    status          VARCHAR(30) DEFAULT 'pending',
    current_subtask TEXT,
    step_current    INTEGER DEFAULT 0,
    step_total      INTEGER DEFAULT 0,
    stats           JSONB DEFAULT '{}',
    input_data      JSONB,
    output_data     JSONB,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER
);
CREATE INDEX idx_agent_runs_task_id ON agent_runs(task_id);
CREATE INDEX idx_agent_runs_agent ON agent_runs(agent_name);

CREATE TABLE log_entries (
    id           BIGSERIAL PRIMARY KEY,
    task_id      UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_run_id UUID REFERENCES agent_runs(id),
    agent_name   VARCHAR(50) NOT NULL,
    log_level    VARCHAR(20) NOT NULL,
    prefix_icon  VARCHAR(5),
    message      TEXT NOT NULL,
    agent_color  VARCHAR(10),
    severity     VARCHAR(20) DEFAULT 'info',
    error_code   VARCHAR(50),
    stack_trace  TEXT,
    is_resolved  BOOLEAN DEFAULT false,
    resolved_at  TIMESTAMPTZ,
    resolved_by  UUID REFERENCES users(id),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_logs_task_id ON log_entries(task_id);
CREATE INDEX idx_logs_agent ON log_entries(agent_name);
CREATE INDEX idx_logs_severity ON log_entries(severity);
CREATE INDEX idx_logs_created ON log_entries(created_at DESC);

CREATE TABLE code_outputs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id      UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_run_id UUID REFERENCES agent_runs(id),
    file_path    VARCHAR(500) NOT NULL,
    file_name    VARCHAR(255) NOT NULL,
    file_type    VARCHAR(50),
    content      TEXT NOT NULL,
    language     VARCHAR(50),
    line_count   INTEGER DEFAULT 0,
    is_new_file  BOOLEAN DEFAULT true,
    is_test_file BOOLEAN DEFAULT false,
    is_doc_file  BOOLEAN DEFAULT false,
    annotations  JSONB DEFAULT '[]',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_code_task_id ON code_outputs(task_id);
CREATE TRIGGER trg_code_outputs_updated_at
    BEFORE UPDATE ON code_outputs
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE user_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,
    device_info TEXT,
    ip_address  VARCHAR(45),
    is_active   BOOLEAN DEFAULT true,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_user_id ON user_sessions(user_id);

CREATE TABLE alert_rules (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id),
    name       VARCHAR(255) NOT NULL,
    condition  JSONB NOT NULL,
    action     JSONB NOT NULL,
    is_active  BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_alert_rules_user ON alert_rules(user_id);