
"""
Safety Guardian (C2) — answers "is this code safe to ship" by combining
Bandit, Semgrep, and Pylint into one verdict instead of leaving three
separate tool outputs for something else to reconcile.

Security findings (Bandit/Semgrep) are blocking. Pylint rides along for
the Reviewer, but a style complaint has never been a reason to send code
back to Coder here.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from safety import bandit_scanner, pylint_checker, semgrep_scanner

BLOCKING_SEVERITIES = {"HIGH", "MEDIUM"}


@dataclass
class SafetyReport:
    passed: bool
    findings: list[dict] = field(default_factory=list)
    quality_score: float = 10.0
    quality_issues: list[dict] = field(default_factory=list)

    def blocking_findings(self) -> list[dict]:
        return [f for f in self.findings if f["severity"] in BLOCKING_SEVERITIES]


async def review(code_files: dict[str, str]) -> SafetyReport:
    bandit_findings, semgrep_findings, quality = await asyncio.gather(
        bandit_scanner.scan(code_files),
        semgrep_scanner.scan(code_files),
        pylint_checker.check(code_files),
    )

    findings = bandit_findings + semgrep_findings
    blocking = any(f["severity"] in BLOCKING_SEVERITIES for f in findings)

    return SafetyReport(
        passed=not blocking,
        findings=findings,
        quality_score=quality["score"],
        quality_issues=quality["issues"],
    )