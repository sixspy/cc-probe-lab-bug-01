"""草稿阈发布读轨审计。"""
from __future__ import annotations

from app.services import draftpub as core
from app.services import draftpub_cutover as cutover
from app.services import draftpub_dualwrite as dual


def audit_summary() -> dict:
    return {
        "title": "草稿阈发布审计",
        "core": core.dashboard(),
        "cutover": cutover.board(),
        "dualwrite": dual.dual_board(),
        "half": core.half_fix_display(),
    }
