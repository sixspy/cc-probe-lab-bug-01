"""争用失败测：发布瞬间双请求灌同号，不得一边新一边旧。

红条件：发布瞬间双请求灌同号，一批报文按新阈、一批按旧阈分流（裂脑）。
"""
import threading
import pytest

from app.services import 装载, 目录, 阈版本


def _同号体(编号: str, 读数: float) -> dict:
    return {
        "批次编号": "测丙",
        "报文": [{
            "报文编号": 编号,
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 读数,
            "观测时": "2026-11-25T09:00:00Z",
        }],
    }


def test_发布瞬间并发装载全部认同一版本():
    目录.改栏规({"PM25上限": "50"})  # 60 将从入栏(旧)变坏点(新)
    同步 = threading.Barrier(3)
    原 = 阈版本.发布同步点

    def _钩子():
        同步.wait(timeout=10)
        原()

    阈版本.发布同步点 = _钩子
    try:
        结果: list[dict] = []
        错误: list[BaseException] = []

        def _装(编号: str):
            try:
                同步.wait(timeout=10)
                结果.append(装载.装一批(_同号体(编号, 60.0)))
            except BaseException as e:  # noqa: BLE001
                错误.append(e)

        def _发():
            try:
                阈版本.发布草稿()
            except BaseException as e:  # noqa: BLE001
                错误.append(e)

        t1 = threading.Thread(target=_装, args=("C-race-1",))
        t2 = threading.Thread(target=_装, args=("C-race-2",))
        tp = threading.Thread(target=_发)
        t1.start(); t2.start(); tp.start()
        t1.join(timeout=20); t2.join(timeout=20); tp.join(timeout=20)
    finally:
        阈版本.发布同步点 = 原

    assert not 错误, f"并发期异常: {错误}"
    assert len(结果) == 2
    版本集 = {r["发布版本"] for r in 结果}
    assert len(版本集) == 1, f"两路装载读出不同发布版本（裂脑）: {版本集}"
    指纹集 = {r["阈指纹"] for r in 结果}
    assert len(指纹集) == 1
    版本 = 版本集.pop()
    assert 版本 in ("v0", "v1")
    # 同版本下同读数必须同命运：要么都入栏(v0/旧)，要么都坏点(v1/新)。
    命运 = {(r["入栏"], r["坏点"]) for r in 结果}
    assert len(命运) == 1, f"同号同读数一边新一边旧: {命运}"
    if 版本 == "v0":
        assert 命运 == {(1, 0)}
    else:
        assert 命运 == {(0, 1)}
    # 发布完成后再灌，必须明确按新阈分流，可与发布瞬间区分。
    后 = 装载.装一批(_同号体("C-race-3", 60.0))
    assert 后["发布版本"] == "v1"
    assert 后["坏点"] == 1 and 后["入栏"] == 0


def test_并发双发布不产生悬空凭证():
    目录.改栏规({"PM25上限": "50"})
    同步 = threading.Barrier(2)
    原 = 阈版本.发布同步点

    def _钩子():
        同步.wait(timeout=10)
        原()

    阈版本.发布同步点 = _钩子
    版本: list[dict] = []
    错误: list[BaseException] = []
    try:
        def _发():
            try:
                版本.append(阈版本.发布草稿())
            except BaseException as e:  # noqa: BLE001
                错误.append(e)

        t1 = threading.Thread(target=_发)
        t2 = threading.Thread(target=_发)
        t1.start(); t2.start()
        t1.join(timeout=20); t2.join(timeout=20)
    finally:
        阈版本.发布同步点 = 原

    assert not 错误
    凭证 = 阈版本.现行凭证()
    历史 = 阈版本.版本历史()
    指纹集 = {v["指纹"] for v in 历史}
    assert 凭证["指纹"] in 指纹集, "凭证指向不存在的阈版本（悬空）"
    对版 = 阈版本.指纹对版(凭证["指纹"])
    assert 对版 is not None
    # 同稿并发发布：要么幂等合成一个 v1，要么串行成 v1/v2，凭证都必须可对账。
    assert 凭证["版本号"] in {v["版本号"] for v in 版本}


def test_并发灌同号幂等且版本一致():
    目录.改栏规({"PM25上限": "50"})
    阈版本.发布草稿()
    结果: list[dict] = []
    错误: list[BaseException] = []

    def _装():
        try:
            结果.append(装载.装一批(_同号体("C-same-id", 60.0)))
        except BaseException as e:  # noqa: BLE001
            错误.append(e)

    t1 = threading.Thread(target=_装)
    t2 = threading.Thread(target=_装)
    t1.start(); t2.start()
    t1.join(timeout=20); t2.join(timeout=20)
    assert not 错误
    assert {r["发布版本"] for r in 结果} == {"v1"}
    入栏合计 = sum(r["入栏"] for r in 结果)
    坏点合计 = sum(r["坏点"] for r in 结果)
    驳回合计 = sum(r["驳回"] for r in 结果)
    # 同号只允许一笔落账，另一笔幂等驳回，且都挂 v1，不允许跨版本分账。
    assert 入栏合计 + 坏点合计 == 1
    assert 驳回合计 == 1
    assert 入栏合计 == 0 and 坏点合计 == 1, "v1 下 60 必须全部按新阈判坏点"


@pytest.mark.parametrize("并发数", [4, 8])
def test_多线程装载指纹无一偏离凭证(并发数):
    目录.改栏规({"PM25上限": "50"})
    阈版本.发布草稿()
    凭证指纹 = 阈版本.现行凭证()["指纹"]
    结果: list[dict] = []
    锁 = threading.Lock()

    def _装(i: int):
        r = 装载.装一批(_同号体(f"C-many-{i}", 60.0))
        with 锁:
            结果.append(r)

    ts = [threading.Thread(target=_装, args=(i,)) for i in range(并发数)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=20)
    assert len(结果) == 并发数
    assert {r["阈指纹"] for r in 结果} == {凭证指纹}
    assert all(r["坏点"] == 1 for r in 结果), "每笔都须按发布的新阈分流"
