# backend/workflow/state.py
"""
Shared state dict passed between every node in the LangGraph workflow.
Only the v1 (six-agent) fields are populated here — v2 fields (risk_score,
grounded, identity_token, curated_items...) get added when those agents
are built in Steps 18-20, not before.
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

    websocket_channel: str
    metrics: dict
    messages: Annotated[list, operator.add]