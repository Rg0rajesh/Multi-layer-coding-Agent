# backend/workflow/state.py
"""
Shared state dict passed between every node in the LangGraph workflow.

v1 fields (plan, code_files, test_results, ...) back the original six-agent
pipeline. The v2 fields below back Guardrail (C9) and Identity Broker (C7),
the two governance agents built in Step 18. Grounding (C8) and Context
Curator (C6) fields aren't added yet — those land when those agents are
built, not before.

Nothing here is wired into workflow/workflow.py yet. That rewiring — adding
all four new nodes to the graph and updating the conditional routing — is
Step 25, once every v2 agent exists.
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict


class WorkflowState(TypedDict, total=False):
    task_id: str
    task_description: str
    language: str
    project_id: Optional[str]
    user_id: str

    plan: Optional[dict]
    code_files: dict
    test_results: Optional[dict]
    review_output: Optional[dict]
    safety_report: Optional[dict]

    plan_approved: bool
    safety_passed: bool
    tests_passed: bool
    coder_retries: int
    replan_count: int
    human_interventions: int
    dynamic_roles: list

    # v2 — Guardrail (C9). risk_score is the post-decay session score,
    # not just this turn's raw classification — see agents/guardrail_agent.py.
    risk_score: float
    risk_verdict: str  # "allow" | "flag" | "block"

    # v2 — Identity Broker (C7). None means no credential was issued
    # (OPA unreachable, or Guardrail blocked before Planner ever ran).
    identity_token: Optional[dict]
   # v2 — Grounding (C8). None until the node has actually run.
    grounded: Optional[bool]
    unsupported_claims: Optional[list]
    
    websocket_channel: str
    metrics: dict
    messages: Annotated[list, operator.add]
 