"""草稿阈发布切流账册：发布瞬间锁指纹、开拒回刷、读轨切到凭证。"""
from __future__ import annotations

from app.db import 连接
from app.services import draftpub as core
from app.services import 阈版本

_SLUG = "draftpub"
_TITLE = "草稿阈发布"
_OK = "发布已亮"


def append_cutover(ref_id: int, note: str = "") -> dict:
    conn = 连接()
    try:
        core._ensure(conn)
        core._set(conn, f"{_SLUG}_cutover_note_{ref_id}", note or _TITLE)
        conn.commit()
    finally:
        conn.close()
    # 真实切流：固化新版本、翻凭证、拒旧阈回刷；无草稿时幂等回当前版本。
    阈版本.发布草稿(note or _TITLE)
    return {
        "ref_id": ref_id,
        "note": note,
        "panel": core.panel_chip(),
        "truth": core.truth_flag(),
        "active_read": core.active_read_ref(),
        "cutover_fp": core.cutover_fp(),
        "reject_refresh": core.reject_refresh(),
        "release_version": 阈版本.现行凭证()["版本号"],
    }


def board() -> dict:
    dash = core.dashboard()
    dash["fate"] = "cutover_book"
    dash["panel_pack_mismatch"] = not dash["aligned"]
    return dash
