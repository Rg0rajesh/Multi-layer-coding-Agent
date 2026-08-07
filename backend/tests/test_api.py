
# backend/tests/test_api.py
"""
API-layer tests for the tasks router. Auth and the DB session are swapped
out via FastAPI's dependency_overrides — no real Postgres connection, just
enough of a fake to satisfy what the router actually awaits.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from database import get_db
from main import app
from models.task import Task
from models.user import User
from services.auth_service import get_current_user
from services.task_service import TaskNotFoundError


@pytest.fixture
def fake_user() -> User:
    return User(id=uuid.uuid4(), email="dev@agentx.local", full_name="Test Dev")


@pytest.fixture
def client(fake_user):
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestCreateTask:
    def test_returns_201_with_created_task(self, client, fake_user, monkeypatch):
        created = Task(
            id=uuid.uuid4(), user_id=fake_user.id, title="Build a REST API",
            status="pending", priority="medium", coordination_pattern="sequential",
            replan_count=0, coder_retries=0, safety_issues_found=0,
            human_interventions=0, review_score=None,
        )
        monkeypatch.setattr("routers.tasks.create_task", AsyncMock(return_value=created))

        response = client.post("/api/v1/tasks", json={"title": "Build a REST API"})

        assert response.status_code == 201
        assert response.json()["title"] == "Build a REST API"

    def test_missing_title_is_rejected(self, client):
        response = client.post("/api/v1/tasks", json={})
        assert response.status_code == 422


class TestGetTask:
    def test_unknown_task_returns_404(self, client, monkeypatch):
        async def _raise(*args, **kwargs):
            raise TaskNotFoundError(uuid.uuid4())

        monkeypatch.setattr("routers.tasks.get_task", _raise)

        response = client.get(f"/api/v1/tasks/{uuid.uuid4()}")
        assert response.status_code == 404


class TestHealthCheck:
    def test_health_endpoint_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}