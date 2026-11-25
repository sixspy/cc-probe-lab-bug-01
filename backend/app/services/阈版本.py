"""阈版本发布与装载读源联剔。

工程形态：旁路凭证表（cutover_book）。
- 草稿只写 ``栏规草稿``，绝不触碰现行 ``栏规`` 阈表；
- 发布在一把进程锁内把整份阈集固化为不可变 ``阈版本`` 行（含指纹），
  再原子翻转单行 ``发布凭证``；装载/校验/结栏只读凭证指向的已发布阈集；
- 旧指纹回刷一律拒绝并在 ``回刷记录`` 留痕。

发布与装载因此认同一发布版本：凭证不翻转，读轨绝不动。
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from app.db import 连接
from app.services import 校验

# 进程级写互斥：发布与装载共用，保证发布瞬间两路灌入读到同一凭证、
# 同号幂等检查与插入原子，杜绝一边新一边旧。
写锁 = threading.RLock()


def _此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# 测试争用注入点：发布事务真正开工前调用。
def 发布同步点() -> None:
    return None


_DDL = """
CREATE TABLE IF NOT EXISTS 栏规草稿 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL,
  更新时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 阈版本 (
  版本号 TEXT PRIMARY KEY,
  指纹 TEXT NOT NULL UNIQUE,
  阈集 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  备注 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 发布凭证 (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  版本号 TEXT NOT NULL,
  指纹 TEXT NOT NULL,
  拒旧阈回刷 INTEGER NOT NULL DEFAULT 0,
  已发布 INTEGER NOT NULL DEFAULT 0,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 回刷记录 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  旧指纹 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  说明 TEXT NOT NULL
);
"""

# 只允许这些键进入阈集，徽标类元数据永远不进指纹。
_阈键 = ("当前栏号", "PM25上限", "PM25下限", "标定偏移上限", "栏策略")


def _ensure(conn) -> None:
    conn.executescript(_DDL)


def _指纹(阈集: dict) -> str:
    文 = json.dumps(阈集, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(文.encode("utf-8")).hexdigest()


def _短指纹(指纹: str) -> str:
    return (指纹 or "")[:12]


def _读现行阈集(conn) -> dict:
    return {
        r["键"]: r["值"]
        for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()
        if r["键"] in _阈键
    }


def _读草稿(conn) -> dict:
    return {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规草稿").fetchall()}


def 初始化(种子阈集: dict | None = None) -> None:
    """建表并落 v0 种子版本与首条凭证；重复初始化不覆盖已发布状态。"""
    conn = 连接()
    try:
        _ensure(conn)
        # 清掉历史脏数据：徽标元数据不得留在现行阈表参与指纹。
        conn.execute("DELETE FROM 栏规 WHERE 键 IN ('草稿发布徽标','发布版本')")
        if conn.execute("SELECT COUNT(*) AS c FROM 发布凭证").fetchone()["c"] == 0:
            阈集 = dict(种子阈集 or _读现行阈集(conn))
            阈集 = {k: v for k, v in 阈集.items() if k in _阈键}
            fp = _指纹(阈集)
            t = _此刻()
            conn.execute(
                "INSERT INTO 阈版本(版本号,指纹,阈集,时刻,备注) VALUES (?,?,?,?,?)",
                ("v0", fp, json.dumps(阈集, ensure_ascii=False), t, "种子阈"),
            )
            conn.execute(
                "INSERT INTO 发布凭证(id,版本号,指纹,拒旧阈回刷,已发布,时刻) VALUES (1,?,?,0,0,?)",
                ("v0", fp, t),
            )
            conn.commit()
    finally:
        conn.close()


def 存草稿(补丁: dict | None) -> dict:
    补丁 = dict(补丁 or {})
    错 = 校验.校验栏规补丁(补丁)
    if 错:
        return {"错误": 校验.摘要错误(错)}
    conn = 连接()
    try:
        _ensure(conn)
        t = _此刻()
        for k, v in 补丁.items():
            if k not in _阈键:
                continue
            conn.execute(
                "INSERT INTO 栏规草稿(键,值,更新时) VALUES (?,?,?) "
                "ON CONFLICT(键) DO UPDATE SET 值=excluded.值, 更新时=excluded.更新时",
                (k, str(v), t),
            )
        conn.commit()
        return {"草稿": 草稿栏规(), "现行": 现行栏规(), "提示": "草稿已存，发布后才进现行读轨"}
    finally:
        conn.close()


def 草稿栏规() -> dict:
    conn = 连接()
    try:
        _ensure(conn)
        现 = _读现行阈集(conn)
        现.update(_读草稿(conn))
        return 现
    finally:
        conn.close()


def 有未发布草稿() -> bool:
    conn = 连接()
    try:
        _ensure(conn)
        return conn.execute("SELECT COUNT(*) AS c FROM 栏规草稿").fetchone()["c"] > 0
    finally:
        conn.close()


def 发布草稿(备注: str = "") -> dict:
    """把草稿固化为新版本并翻转凭证；同稿重复发布幂等。"""
    # 同步点在锁外，争用测试可在锁竞争前同时放行发布者与装载者。
    发布同步点()
    with 写锁:
        conn = 连接()
        try:
            _ensure(conn)
            conn.execute("PRAGMA busy_timeout = 5000")
            旧凭证 = _凭证行(conn)
            阈集 = _读现行阈集(conn)
            阈集.update(_读草稿(conn))
            阈集 = {k: v for k, v in 阈集.items() if k in _阈键}
            fp = _指纹(阈集)
            t = _此刻()

            if 旧凭证 and fp == 旧凭证["指纹"]:
                # 幂等：同稿重复发布不裂新版本。
                conn.execute("DELETE FROM 栏规草稿")
                conn.commit()
                return {
                    "版本号": 旧凭证["版本号"],
                    "指纹": fp,
                    "短指纹": _短指纹(fp),
                    "幂等": True,
                }

            序号 = conn.execute("SELECT COUNT(*) AS c FROM 阈版本").fetchone()["c"]
            版本号 = f"v{序号}"
            # 先落不可变版本行，再翻转凭证：读者永远能凭指纹对到版。
            conn.execute(
                "INSERT INTO 阈版本(版本号,指纹,阈集,时刻,备注) VALUES (?,?,?,?,?)",
                (版本号, fp, json.dumps(阈集, ensure_ascii=False), t, 备注 or "草稿发布"),
            )
            conn.execute(
                "UPDATE 发布凭证 SET 版本号=?, 指纹=?, 拒旧阈回刷=1, 已发布=1, 时刻=? WHERE id=1",
                (版本号, fp, t),
            )
            # 草稿转正：现行阈表与草稿清账同步。
            for k, v in 阈集.items():
                conn.execute(
                    "INSERT INTO 栏规(键,值) VALUES (?,?) "
                    "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
                    (k, v),
                )
            conn.execute("DELETE FROM 栏规草稿")
            conn.commit()
            return {
                "版本号": 版本号,
                "指纹": fp,
                "短指纹": _短指纹(fp),
                "幂等": False,
                "阈集": 阈集,
            }
        finally:
            conn.close()


def _凭证行(conn) -> dict | None:
    _ensure(conn)
    r = conn.execute("SELECT * FROM 发布凭证 WHERE id=1").fetchone()
    return dict(r) if r else None


def 现行凭证() -> dict:
    conn = 连接()
    try:
        行 = _凭证行(conn)
        if 行 is None:
            初始化()
            行 = _凭证行(conn)
        return {
            "版本号": 行["版本号"],
            "指纹": 行["指纹"],
            "短指纹": _短指纹(行["指纹"]),
            "拒旧阈回刷": int(行["拒旧阈回刷"]),
            "已发布": bool(行["已发布"]),
            "时刻": 行["时刻"],
        }
    finally:
        conn.close()


def 指纹对版(指纹: str) -> dict | None:
    conn = 连接()
    try:
        _ensure(conn)
        r = conn.execute(
            "SELECT 版本号,指纹,时刻,备注 FROM 阈版本 WHERE 指纹=?", (指纹,)
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def 现行栏规() -> dict:
    """装载/校验/结栏唯一读源：凭证指纹指向的已发布阈集。"""
    凭证 = 现行凭证()
    conn = 连接()
    try:
        _ensure(conn)
        r = conn.execute(
            "SELECT 阈集 FROM 阈版本 WHERE 指纹=?", (凭证["指纹"],)
        ).fetchone()
        if r is None:  # 凭证悬空即数据事故，宁可不读。
            raise RuntimeError("发布凭证悬空：指纹对不到已发布阈版本")
        return json.loads(r["阈集"])
    finally:
        conn.close()


def 版本历史() -> list[dict]:
    conn = 连接()
    try:
        _ensure(conn)
        return [
            {
                "版本号": r["版本号"],
                "指纹": r["指纹"],
                "短指纹": _短指纹(r["指纹"]),
                "时刻": r["时刻"],
                "备注": r["备注"],
            }
            for r in conn.execute(
                "SELECT 版本号,指纹,时刻,备注 FROM 阈版本 ORDER BY 版本号"
            ).fetchall()
        ]
    finally:
        conn.close()


def 拒旧阈回刷(旧指纹: str, 说明: str = "") -> dict:
    """任何与现行凭证不符的指纹回刷一律拒绝并留痕。"""
    凭证 = 现行凭证()
    拒绝 = 旧指纹 != 凭证["指纹"]
    conn = 连接()
    try:
        _ensure(conn)
        if 拒绝:
            conn.execute(
                "INSERT INTO 回刷记录(旧指纹,时刻,说明) VALUES (?,?,?)",
                (旧指纹, _此刻(), 说明 or "旧阈指纹回刷被拒"),
            )
            conn.commit()
        return {"拒绝": 拒绝, "现行指纹": 凭证["指纹"], "旧指纹": 旧指纹}
    finally:
        conn.close()


def 回刷记录() -> list[dict]:
    conn = 连接()
    try:
        _ensure(conn)
        return [dict(r) for r in conn.execute(
            "SELECT 编号,旧指纹,时刻,说明 FROM 回刷记录 ORDER BY 编号 DESC"
        ).fetchall()]
    finally:
        conn.close()


def 栏规对账() -> dict:
    凭证 = 现行凭证()
    对版 = 指纹对版(凭证["指纹"])
    待发 = 有未发布草稿()
    齐套 = (
        凭证["已发布"]
        and not 待发
        and 对版 is not None
        and 凭证["拒旧阈回刷"] == 1
    )
    return {
        "齐套": 齐套,
        "有未发布草稿": 待发,
        "现行版本": 凭证["版本号"],
        "现行指纹": 凭证["指纹"],
        "短指纹": 凭证["短指纹"],
        "草稿版本": None if 待发 else (凭证["版本号"] if 凭证["已发布"] else None),
        "凭证可对版": 对版 is not None,
        "拒旧阈回刷": 凭证["拒旧阈回刷"] == 1,
        "时刻": 凭证["时刻"],
    }


def 看板() -> dict:
    对账 = 栏规对账()
    return {
        "发布版本": {
            "版本号": 对账["现行版本"],
            "指纹": 对账["现行指纹"],
            "短指纹": 对账["短指纹"],
            "齐套": 对账["齐套"],
            "有未发布草稿": 对账["有未发布草稿"],
        },
        "版本历史": 版本历史(),
        "回刷记录": 回刷记录(),
        "对账": 对账,
    }
