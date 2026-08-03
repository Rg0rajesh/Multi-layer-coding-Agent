# backend/services/output_service.py
"""
Everything Code Output needs: listing files for a task, building the tree
the frontend renders, fetching one file's content, and zipping the lot up
for download. Kept HTTP-agnostic like task_service.py — routers/outputs.py
just translates this into responses.
"""
from __future__ import annotations

import io
import zipfile
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.code_output import CodeOutput


class OutputNotFoundError(Exception):
    def __init__(self, output_id: UUID):
        self.output_id = output_id
        super().__init__(f"Code output {output_id} not found")


async def list_outputs(db: AsyncSession, *, task_id: UUID) -> list[CodeOutput]:
    # One query, ordered so the tree builder below doesn't have to sort.
    result = await db.execute(
        select(CodeOutput).where(CodeOutput.task_id == task_id).order_by(CodeOutput.file_path)
    )
    return list(result.scalars().all())


async def get_output(db: AsyncSession, *, task_id: UUID, output_id: UUID) -> CodeOutput:
    result = await db.execute(
        select(CodeOutput).where(CodeOutput.id == output_id, CodeOutput.task_id == task_id)
    )
    output = result.scalar_one_or_none()
    if output is None:
        raise OutputNotFoundError(output_id)
    return output


def build_file_tree(outputs: list[CodeOutput]) -> dict:
    """
    Turns a flat list of file_paths into the nested {name, type, children}
    shape the frontend's file tree component expects.

    O(n * d) where d = path depth (small, bounded — rarely past 5-6 levels),
    so this is effectively linear in the number of files. No sorting, no
    repeated scans — each file is placed with one walk down the tree.
    """
    root: dict = {"name": "root", "type": "folder", "children": {}}

    for output in outputs:
        parts = output.file_path.strip("/").split("/")
        node = root
        for i, part in enumerate(parts):
            is_file = i == len(parts) - 1
            children = node["children"]

            if part not in children:
                children[part] = (
                    _file_node(output) if is_file else {"name": part, "type": "folder", "children": {}}
                )
            node = children[part]

    return _to_list_form(root)


def _file_node(output: CodeOutput) -> dict:
    return {
        "name": output.file_name,
        "type": "file",
        "id": str(output.id),
        "file_type": output.file_type,
        "language": output.language,
        "line_count": output.line_count,
        "is_new_file": output.is_new_file,
        "is_test_file": output.is_test_file,
    }


def _to_list_form(node: dict) -> dict:
    """Recursively swaps the dict-keyed 'children' used for O(1) insertion
    above into a sorted list, which is what actually serializes cleanly to
    JSON and what a tree component wants to render."""
    if node["type"] == "file":
        return node

    children = sorted(node["children"].values(), key=lambda n: (n["type"] != "folder", n["name"]))
    return {**node, "children": [_to_list_form(child) for child in children]}


def build_zip(outputs: list[CodeOutput]) -> io.BytesIO:
    """Zips every file for a task into memory. Fine at task scale (dozens
    of generated files, not thousands) — if that assumption ever breaks,
    switch to writing to a temp file instead of holding it all in RAM."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for output in outputs:
            archive.writestr(output.file_path, output.content)

    buffer.seek(0)
    return buffer