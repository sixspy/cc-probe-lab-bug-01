"""草稿阈发布双写两轨：旧阈留只读归档，现行读轨仍以旁路凭证为准。

双写只做镜像归档演示，不接管读轨；未被选为现行读轨时不得谎报对齐。
"""
from __future__ import annotations

from app.db import 连接
from app.services import draftpub as core
from app.services import 阈版本

_SLUG = "draftpub"
_TITLE = "草稿阈发布"
_OK = "发布已亮"


def apply_dualwrite(note: str = "") -> dict:
    conn = 连接()
    try:
        core._ensure(conn)
        core._set(conn, f"{_SLUG}_dual_chip", _OK)
        core._set(conn, f"{_SLUG}_dual_note", note or _TITLE)
        # 版本史即只读归档，逐版留档；不写 live_flag，读轨不切。
        for v in 阈版本.版本历史():
            core._set(conn, f"{_SLUG}_archive_{v['版本号']}", v["指纹"])
        conn.commit()
    finally:
        conn.close()
    return {
        "dual_chip": _OK,
        "truth": core.truth_flag(),
        "active_read": core.active_read_ref(),
        "archive_count": len(core.archive_rows()),
        "live_flag": core.live_flag(),
        "release_version": 阈版本.现行凭证()["版本号"],
    }


def dual_board() -> dict:
    apply_dualwrite()
    dash = core.dashboard()
    return {
        "dual_chip": _OK,
        "truth": core.truth_flag(),
        "active_read": core.active_read_ref(),
        "archive": core.archive_rows(),
        "live_flag": core.live_flag(),
        "dash": dash,
        "fate": "dualwrite",
        "panel_pack_mismatch": not dash["aligned"],
        "title": f"{_TITLE}双写面",
    }
