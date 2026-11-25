#!/usr/bin/env python3
"""题面复现：改草稿点发布后再灌越阈夹具。

旧实现：页上新阈绿而实闸旧值——草稿改 PM25 上限 50 后，
60 的越新阈点仍按种子旧阈 75 入栏。
修复后：发布前 60 按 v0 入栏；发布后 60 按 v1 进坏点匣。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

_临时 = Path(tempfile.mkdtemp(prefix="draftpub-repro-"))
db.数据目录 = _临时
db.库路径 = _临时 / "探栏.db"

from app import seed  # noqa: E402
from app.services import 装载, 目录, 阈版本  # noqa: E402


def _体(编号: str) -> dict:
    return {
        "批次编号": "复现",
        "报文": [{
            "报文编号": 编号,
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 60.0,
            "观测时": "2026-11-25T11:00:00Z",
        }],
    }


def main() -> int:
    seed.初始化库()
    失败 = False

    # 1) 草稿改成 50，但不发布：现行仍是种子 75，60 入栏。
    目录.改栏规({"PM25上限": "50"})
    对账 = 阈版本.栏规对账()
    print(f"[1] 存草稿后：现行版本={对账['现行版本']} 待发草稿={对账['有未发布草稿']} 齐套={对账['齐套']}")
    if 阈版本.现行栏规()["PM25上限"] != "75":
        print("红：草稿污染了现行阈表"); 失败 = True
    r1 = 装载.装一批(_体("REPRO-1"))
    print(f"    灌 60 → 版本={r1['发布版本']} 入栏={r1['入栏']} 坏点={r1['坏点']}")
    if not (r1["发布版本"] == "v0" and r1["入栏"] == 1 and r1["坏点"] == 0):
        print("红：未发布草稿影响了装载"); 失败 = True

    # 2) 发布：凭证翻转，现行读轨切到 v1。
    发布 = 阈版本.发布草稿()
    print(f"[2] 发布：版本={发布['版本号']} 指纹={发布['短指纹']}")
    对账 = 阈版本.栏规对账()
    if not (对账["齐套"] and 阈版本.现行栏规()["PM25上限"] == "50"):
        print("红：发布后凭证/阈集未对齐"); 失败 = True

    # 3) 发布后再灌同一越新阈点：必须按新阈进坏点匣。
    r2 = 装载.装一批(_体("REPRO-2"))
    print(f"[3] 发布后灌 60 → 版本={r2['发布版本']} 入栏={r2['入栏']} 坏点={r2['坏点']}")
    if not (r2["发布版本"] == "v1" and r2["入栏"] == 0 and r2["坏点"] == 1):
        print("红：发布后仍按旧阈分流（页绿实旧）"); 失败 = True

    # 4) 旧指纹回刷被拒。
    闸 = 阈版本.拒旧阈回刷(r1["阈指纹"])
    print(f"[4] 旧指纹回刷：拒绝={闸['拒绝']}；回刷记录={len(阈版本.回刷记录())} 条")
    if not 闸["拒绝"]:
        print("红：旧阈指纹回刷未被拒绝"); 失败 = True

    print("绿：草稿/发布/装载读轨联剔成立。" if not 失败 else "复现脚本见红。")
    return 0 if not 失败 else 1


if __name__ == "__main__":
    raise SystemExit(main())
