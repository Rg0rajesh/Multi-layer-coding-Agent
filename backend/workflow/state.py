# backend/workflow/state.py
"""
Shared state dict passed between every node in the LangGraph workflow.
Backs the full 10-node v2.1 pipeline:

  Guardrail -> Planner -> Grounding -> Human -> Identity Broker
    -> Coder -> Tester -> Security -> Reviewer -> Context Curator

Every field a node reads or writes needs to be declared here — TypedDict
isn't enforced at runtime, so a missing field won't crash anything, but it
does mean static type checkers (and the next person reading this file)
have an incomplete picture of what actually flows through the graph.
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

    # Guardrail (C9). risk_score is the post-decay session score, not just
    # this turn's raw classification — see agents/guardrail_agent.py.
    risk_score: float
    risk_verdict: str  # "allow" | "flag" | "block"

    # Identity Broker (C7). None means no credential was issued (OPA
    # unreachable, or Guardrail blocked before Planner ever ran).
    identity_token: Optional[dict]

    # Grounding (C8).
    grounded: Optional[bool]
    unsupported_claims: Optional[list]

    # Context Curator (C6). Written by context_curator_node, read back in
    # workflow.py's run_task_workflow() for the run summary.
    curated_items: Optional[list]

    websocket_channel: str
    metrics: dict
    messages: Annotated[list, operator.add]