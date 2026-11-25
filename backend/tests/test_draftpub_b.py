"""失败测乙：栏规对账不得把草稿徽标当已发布齐套绿。

红条件：目录把草稿行标成已发布徽标即齐套绿；半修只改栏规页不改校验读源仍失败。
"""
from app.services import 装载, 目录, 阈版本
from app.services import draftpub as core
from app.services import draftpub_cutover as cutover
from app.services import draftpub_dualwrite as dual


def test_仅存草稿时齐套灯不得绿():
    目录.改栏规({"PM25上限": "50"})
    对账 = 阈版本.栏规对账()
    assert 对账["有未发布草稿"] is True
    assert 对账["齐套"] is False
    assert 对账["现行版本"] == "v0"
    assert 对账["草稿版本"] is None
    # draftpub 看板不得在未发布时亮绿；假绿只可能由半修刷漆制造。
    snap = core.dashboard()
    assert snap["aligned"] is False
    assert snap["panel_chip"] != "发布已亮"
    assert snap["panel_pack_mismatch"] is False


def test_半修只亮灯不改读源仍判未对齐():
    # half_fix_display 只刷面板芯片，读轨不动 → 必须仍判未对齐。
    core.half_fix_display()
    snap = core.dashboard()
    assert snap["panel_chip"] == "发布已亮"
    assert snap["truth"] == "阈源仍旧", "刷漆改不动真相"
    assert snap["aligned"] is False
    assert snap["panel_pack_mismatch"] is True, "单点刷漆即假绿，必须被识破"
    齐套 = 目录.draftpub_齐套灯()
    assert 齐套["齐套"] == 齐套["对齐实值"]
    assert 齐套["齐套"] is False


def test_真实发布后齐套才绿且徽标属实():
    目录.改栏规({"PM25上限": "50"})
    发布 = 阈版本.发布草稿()
    对账 = 阈版本.栏规对账()
    assert 对账["齐套"] is True
    assert 对账["有未发布草稿"] is False
    assert 对账["现行版本"] == "v1"
    assert 对账["现行指纹"] == 发布["指纹"]
    snap = core.dashboard()
    assert snap["aligned"] is True
    assert snap["panel_pack_mismatch"] is False
    assert snap["panel_chip"] == snap["truth"] == "发布已亮"
    齐套 = 目录.draftpub_齐套灯()
    assert 齐套["齐套"] is True
    assert 齐套["对齐实值"] is True


def test_切流面板走真实发布不再空壳亮绿():
    目录.改栏规({"PM25上限": "50"})
    果 = cutover.append_cutover(1, "测乙切流")
    assert 果["active_read"] == "cutover_book"
    assert 果["reject_refresh"] is True
    assert 果["cutover_fp"] not in ("", "stale-fp")
    board = cutover.board()
    assert board["aligned"] is True
    assert board["panel_pack_mismatch"] is False
    # 发布版本在对账与看板两侧一致。
    assert 阈版本.现行凭证()["版本号"] == board["release_version"]


def test_双写面板未采纳时不得谎报对齐():
    out = dual.apply_dualwrite("测乙双写")
    assert out["archive_count"] >= 0
    # 双写仅作镜像演示，未被选为现行读轨时不得谎报。
    assert out["active_read"] == core.active_read_ref()
    board = dual.dual_board()
    assert board["panel_pack_mismatch"] == (not core.dashboard()["aligned"])


def test_概览携带可见发布版本():
    目录.改栏规({"PM25上限": "50"})
    阈版本.发布草稿()
    o = 目录.概览()
    assert "发布版本" in o
    assert o["发布版本"]["版本号"] == "v1"
    assert o["发布版本"]["指纹"]
    assert o["栏规"]["PM25上限"] == "50"


def test_栏规读接口区分现行与草稿():
    目录.改栏规({"PM25上限": "50"})
    现 = 目录.栏规()
    assert 现["PM25上限"] == "75", "现行阈在发布前必须保持种子值"
    草 = 目录.草稿栏规()
    assert 草["PM25上限"] == "50"
    assert "草稿发布徽标" not in 现 and "发布版本" not in 现, "徽标元数据不得污染现行阈表"
