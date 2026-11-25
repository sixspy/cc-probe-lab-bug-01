#!/usr/bin/env python3
"""收工并发双请求脚本：发布瞬间两路同灌，验证不裂脑。

用法（在 backend 目录、激活 venv 后）：
    python scripts/并发双请求.py

场景：先把 PM25 上限草稿改成 50（60 在旧阈入栏、新阈坏点），
随后用屏障让「发布线程」与两个「装载线程」同时放行，
断言两路装载报告挂同一发布版本、同一阈指纹、同一命运。
"""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

# 独立临时库，不碰运行数据。
_临时 = Path(tempfile.mkdtemp(prefix="draftpub-race-"))
db.数据目录 = _临时
db.库路径 = _临时 / "探栏.db"

from app.db import 连接  # noqa: E402
from app.services import 装载, 目录, 阈版本  # noqa: E402


def _体(编号: str) -> dict:
    return {
        "批次编号": "并发脚本",
        "报文": [{
            "报文编号": 编号,
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 60.0,
            "观测时": "2026-11-25T10:00:00Z",
        }],
    }


def main() -> int:
    # 干净库：临时目录内初始化。
    连接().close()
    from app import seed
    seed.初始化库()

    目录.改栏规({"PM25上限": "50"})
    屏障 = threading.Barrier(3)
    原钩子 = 阈版本.发布同步点

    def _钩子() -> None:
        屏障.wait(timeout=15)
        原钩子()

    阈版本.发布同步点 = _钩子
    结果: list[dict] = []
    异常: list[BaseException] = []

    def _装(编号: str) -> None:
        try:
            屏障.wait(timeout=15)
            结果.append(装载.装一批(_体(编号)))
        except BaseException as e:  # noqa: BLE001
            异常.append(e)

    def _发() -> None:
        try:
            阈版本.发布草稿()
        except BaseException as e:  # noqa: BLE001
            异常.append(e)

    t1 = threading.Thread(target=_装, args=("R-1",))
    t2 = threading.Thread(target=_装, args=("R-2",))
    tp = threading.Thread(target=_发)
    t1.start(); t2.start(); tp.start()
    for t in (t1, t2, tp):
        t.join(timeout=30)
    阈版本.发布同步点 = 原钩子

    if 异常:
        print("红：并发期异常", 异常)
        return 1
    版本 = {r["发布版本"] for r in 结果}
    指纹 = {r["阈指纹"] for r in 结果}
    命运 = {(r["入栏"], r["坏点"]) for r in 结果}
    print("两路装载报告：")
    for r in 结果:
        print(f"  版本={r['发布版本']} 指纹={r['阈指纹'][:12]} 入栏={r['入栏']} 坏点={r['坏点']}")
    if not (len(版本) == 1 and len(指纹) == 1 and len(命运) == 1):
        print("红：发布瞬间一边新一边旧（裂脑）")
        return 1
    后 = 装载.装一批(_体("R-3"))
    print(f"发布后再灌：版本={后['发布版本']} 坏点={后['坏点']} 入栏={后['入栏']}")
    if 后["发布版本"] != "v1" or 后["坏点"] != 1:
        print("红：发布后再灌未按新阈分流")
        return 1
    print("绿：发布瞬间两路同版本同指纹同命运，发布后明确按新阈分流。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
