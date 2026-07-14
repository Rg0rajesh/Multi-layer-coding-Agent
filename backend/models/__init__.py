# backend/models/__init__.py
# Import order matters for SQLAlchemy relationship string resolution —
# keep this even though it looks redundant with the individual files.
from .user import User
from .team import Team, TeamMember
from .project import Project
from .task import Task
from .agent_run import AgentRun
from .log_entry import LogEntry
from .code_output import CodeOutput
from .user_session import AlertRule, UserSession
from .session_risk import SessionRiskScore       # v2 — C9 Guardrail
from .identity_token import IdentityToken        # v2 — C7 Identity Broker
from .curated_memory import CuratedMemory        # v2 — C6 Context Curator

__all__ = [
    "User", "Team", "TeamMember", "Project", "Task",
    "AgentRun", "LogEntry", "CodeOutput", "UserSession", "AlertRule",
    "SessionRiskScore", "IdentityToken", "CuratedMemory",
]