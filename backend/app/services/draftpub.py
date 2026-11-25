"""草稿阈发布收口面：面板芯片必须与读轨凭证同真同假。

读轨真相由 ``app.services.阈版本`` 的发布凭证裁定：
- 未发布：面板不得亮绿，active_read 停在 old_track；
- 已发布：active_read=cutover_book，指纹可对版、拒旧阈回刷打开。
"""
from __future__ import annotations

from app.db import 连接
from app.services import 阈版本

_SLUG = "draftpub"
_OK = "发布已亮"
_BAD = "阈源仍旧"
_TITLE = "草稿阈发布"
_OLD = "old_track"
_CUTOVER = "cutover_book"
_LIVE = "live_flag"


def _ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS 探栏元("
        "键 TEXT PRIMARY KEY, 值 TEXT NOT NULL)"
    )


def _get(conn, key: str, default: str = "") -> str:
    _ensure(conn)
    r = conn.execute("SELECT 值 FROM 探栏元 WHERE 键=?", (key,)).fetchone()
    return r["值"] if r else default


def _set(conn, key: str, value: str) -> None:
    _ensure(conn)
    conn.execute(
        "INSERT INTO 探栏元(键,值) VALUES (?,?) "
        "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
        (key, value),
    )


def panel_chip() -> str:
    """页面显示芯片：含半修单点刷上的“漆”，可能与真相不符（假绿）。

    凭证已齐套时显示漆自动跟上真相，保证真实发布后页灯即绿。
    """
    if 阈版本.栏规对账()["齐套"]:
        return _OK
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_panel_chip", _BAD)
    finally:
        conn.close()


def truth_flag() -> str:
    """真相芯片：只跟发布凭证走，面板刷漆改不动它。"""
    return _OK if 阈版本.栏规对账()["齐套"] else _BAD


def active_read_ref() -> str:
    凭证 = 阈版本.现行凭证()
    if 凭证["已发布"] and 凭证["拒旧阈回刷"] == 1:
        return _CUTOVER
    return _OLD


def cutover_fp() -> str:
    凭证 = 阈版本.现行凭证()
    return 凭证["指纹"] if 凭证["已发布"] else ""


def reject_refresh() -> bool:
    return 阈版本.现行凭证()["拒旧阈回刷"] == 1


def live_flag() -> str:
    # 旁路凭证形态不启用 live_flag 轨；双写形态才写。
    conn = 连接()
    try:
        return _get(conn, f"{_SLUG}_live_flag", "")
    finally:
        conn.close()


def archive_rows() -> list[dict]:
    # 版本史即旧阈只读归档。
    return [
        {"键": v["版本号"], "值": v["指纹"], "时刻": v["时刻"], "备注": v["备注"]}
        for v in 阈版本.版本历史()
    ]


def paint_ok() -> str:
    """半修演示：仅点亮面板元数据，读轨凭证不动。

    真正的 snapshot 仍会因 active_read=old_track 判未对齐——
    这正是“禁止单点改徽标救齐三红”的保证。
    """
    conn = 连接()
    try:
        _set(conn, f"{_SLUG}_panel_chip", _OK)
        _set(conn, f"{_SLUG}_display_only", "1")
        conn.commit()
        return _OK
    finally:
        conn.close()


def commit_action(payload: dict | None = None) -> dict:
    """发布动作：有挂起草稿则真实发布，否则仅回当前真相，不再写假绿。"""
    payload = payload or {}
    conn = 连接()
    try:
        c = int(_get(conn, f"{_SLUG}_counter", "0") or "0") + 1
        _set(conn, f"{_SLUG}_counter", str(c))
        _set(conn, f"{_SLUG}_last_payload", str(payload)[:200])
        conn.commit()
    finally:
        conn.close()

    发布 = None
    if 阈版本.有未发布草稿():
        发布 = 阈版本.发布草稿(str(payload.get("note") or _TITLE))
    # 真实发布后把显示漆刷成与凭证一致；无发布则不制造假绿。
    if 发布 is not None:
        conn = 连接()
        try:
            _set(conn, f"{_SLUG}_panel_chip", panel_chip() if not 阈版本.栏规对账()["齐套"] else _OK)
            conn.commit()
        finally:
            conn.close()
    snap = snapshot()
    return {
        "ok": True,
        "chip": snap["panel_chip"],
        "title": _TITLE,
        "counter": c,
        "active_read": snap["active_read"],
        "cutover_fp": snap["cutover_fp"],
        "reject_refresh": snap["reject_refresh"],
        "archive_count": snap["archive_count"],
        "live_flag": snap["live_flag"],
        "release_version": 阈版本.现行凭证()["版本号"],
        "published": 发布,
        "message": f"{_TITLE}已落台" if 发布 else f"{_TITLE}无挂起草稿，读轨未变",
    }


def half_fix_display() -> dict:
    paint_ok()
    return {
        "panel_chip": panel_chip(),
        "truth": truth_flag(),
        "active_read": active_read_ref(),
        "archive_count": len(archive_rows()),
        "half_fixed": True,
    }


def snapshot() -> dict:
    对账 = 阈版本.栏规对账()
    ref = active_read_ref()
    chip = panel_chip()
    truth = truth_flag()
    arch = archive_rows()
    aligned = (
        对账["齐套"]
        and truth == _OK
        and ref == _CUTOVER
        and 对账["拒旧阈回刷"]
        and 对账["凭证可对版"]
        and cutover_fp() not in ("", "stale-fp")
    )
    # 假绿：显示漆亮绿但真相未对齐。
    假绿 = chip == _OK and not aligned
    return {
        "title": _TITLE,
        "panel_chip": chip,
        "truth": truth,
        "active_read": ref,
        "cutover_fp": cutover_fp(),
        "reject_refresh": reject_refresh(),
        "archive_count": len(arch),
        "live_flag": live_flag(),
        "aligned": aligned,
        "panel_pack_mismatch": 假绿,
        "gate_bypass": not aligned,
        "release_version": 对账["现行版本"],
        "release_fp": 对账["现行指纹"],
        "has_pending_draft": 对账["有未发布草稿"],
    }


def dashboard() -> dict:
    snap = snapshot()
    return {
        **snap,
        "ok_chip": _OK,
        "bad_chip": _BAD,
        "label": _TITLE,
        "read_tracks": {
            "old_track": _OLD,
            "cutover_book": _CUTOVER,
            "live_flag": _LIVE,
        },
    }


def reconcile_display() -> dict:
    return half_fix_display()
