
# backend/memory/memory_manager.py
"""
Coordinates all three memory tiers for the agents. Planner/Coder/Reviewer
call through here instead of touching ChromaDB or Mem0 directly — keeps
the "Tier 2 only gets written through Context Curator" rule enforced in
one place instead of every agent having to remember it independently.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from memory.developer_memory import DeveloperMemory
from memory.project_memory import ProjectMemory
from memory.task_memory import TaskMemory


@dataclass
class MemoryContext:
    task_notes: list[dict] = field(default_factory=list)
    project_knowledge: list[dict] = field(default_factory=list)
    developer_profile: dict = field(default_factory=dict)

    def as_prompt_block(self) -> str:
        """Flattened into something an agent's system/user prompt can just
        drop in — avoids every agent file writing its own formatting."""
        lines = []
        if self.developer_profile.get("preferences"):
            lines.append("Developer preferences: " + "; ".join(self.developer_profile["preferences"]))
        if self.project_knowledge:
            lines.append("Known project context:")
            lines += [f"- {item['content']}" for item in self.project_knowledge]
        if self.task_notes:
            lines.append("Recent task activity:")
            lines += [f"- {item['content']}" for item in self.task_notes]
        return "\n".join(lines)


class MemoryManager:
    def __init__(self, task_id: str, user_id: str, project_id: str | None = None):
        self.task_memory = TaskMemory(task_id)
        self.project_memory = ProjectMemory(project_id) if project_id else None
        self.developer_memory = DeveloperMemory(user_id)

    async def build_agent_context(self, query: str) -> MemoryContext:
        task_notes, project_knowledge, profile = await asyncio.gather(
            self.task_memory.recall(query),
            self.project_memory.recall(query) if self.project_memory else _empty_list(),
            self.developer_memory.get_profile(),
        )
        return MemoryContext(task_notes=task_notes, project_knowledge=project_knowledge, developer_profile=profile)

    async def finalize_task(self) -> None:
        """Call once after Reviewer (or Context Curator, once v2 agents are
        wired in) finishes — wipes Tier 1, leaves Tiers 2/3 untouched."""
        await self.task_memory.clear()


async def _empty_list() -> list:
    return []