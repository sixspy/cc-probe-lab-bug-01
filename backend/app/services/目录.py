"""列表与栏规。"""
from __future__ import annotations
from app.db import 连接
from app.services import 校验, 阈版本


def 栏规() -> dict:
    # 唯一现行读源：发布凭证指向的已发布阈集，草稿不入此表返回。
    return 阈版本.现行栏规()


def 草稿栏规() -> dict:
    return 阈版本.草稿栏规()


def 改栏规(体: dict) -> dict:
    # 草稿只进草稿台，绝不直写现行阈表；发布后才换凭证、换读源。
    体 = dict(体 or {})
    体.pop("草稿发布徽标", None)
    体.pop("发布版本", None)
    错 = 校验.校验栏规补丁(体)
    if 错:
        return {"错误": 校验.摘要错误(错), "栏规": 栏规(), "草稿": 草稿栏规()}
    存 = 阈版本.存草稿(体)
    if "错误" in 存:
        return {"错误": 存["错误"], "栏规": 栏规(), "草稿": 草稿栏规()}
    return {
        "栏规": 存["现行"],
        "草稿": 存["草稿"],
        "提示": 存["提示"],
        "发布版本": 阈版本.现行凭证()["版本号"],
    }


def 站点列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 站点源 ORDER BY 源键").fetchall()]
    finally:
        conn.close()


def 报文列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 观测报文 ORDER BY 观测时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 缓冲列表(命运: str | None = None) -> list[dict]:
    conn = 连接()
    try:
        if 命运:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM 入栏缓冲 WHERE 命运=? ORDER BY 观测时", (命运,)
                ).fetchall()
            ]
        return [dict(r) for r in conn.execute("SELECT * FROM 入栏缓冲 ORDER BY 观测时").fetchall()]
    finally:
        conn.close()


def 汇总列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 站点汇总账 ORDER BY 物化时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 坏点列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 坏点匣 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 贯验列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 栏贯验 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 概览():
    # draftpub panel inject
    pass


def __概览_orig():
    raise RuntimeError


def 概览_broken_placeholder():
    return {}


def 概览() -> dict:
    conn = 连接()
    try:
        return {
            "观测报文": conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"],
            "在栏": conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'").fetchone()["c"],
            "站点汇总": conn.execute("SELECT COUNT(*) AS c FROM 站点汇总账").fetchone()["c"],
            "坏点": conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"],
            "栏规": 栏规(),
            "发布版本": 阈版本.看板()["发布版本"],
        }
    finally:
        conn.close()


def 装载批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,时刻,入流,入栏,坏点 FROM 装载批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 结栏批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,栏号,时刻,汇总数 FROM 结栏批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 站点查(源键: str) -> dict | None:
    conn = 连接()
    try:
        r = conn.execute("SELECT * FROM 站点源 WHERE 源键=?", (源键,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()



def draftpub_齐套灯() -> dict:
    """齐套灯：只认真实对齐（凭证对版 + 无挂起草稿 + 拒回刷），不看面板芯片。"""
    from app.services import draftpub as _m
    snap = _m.dashboard()
    return {
        "标题": snap.get("title"),
        "芯片": snap.get("panel_chip"),
        "真相": snap.get("truth"),
        "齐套": bool(snap.get("aligned")),
        "对齐实值": snap.get("aligned"),
        "panel_pack_mismatch": snap.get("panel_pack_mismatch", True),
    }
