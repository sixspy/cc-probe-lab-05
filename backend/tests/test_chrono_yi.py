"""乙（乙形态：双写两轨）。

- 收到序进只读归档（影子轨），现行入栏缓冲改读观测时序，两轨读引用不同。
- 失败测乙：汇总影子序与现行缓冲序拧花却亮对齐则红——
  数对得上但序拧花时，序对账必须判撕裂，不许只凭笔数亮对齐。
"""
from __future__ import annotations

from app.db import 连接
from app.services import 装载, 结栏, 贯验


def _报文(编号: str, 观测时: str, 读数: float = 31.0, 站点: str = "站-河东") -> dict:
    return {
        "报文编号": 编号,
        "站点键": 站点,
        "指标键": "PM25",
        "读数": 读数,
        "观测时": 观测时,
    }


def _影子轨序() -> list[str]:
    """收到序归档（只读影子轨）按到达序给出的报文序。"""
    from app.services import 影子序

    return [r["报文编号"] for r in 影子序.归档列表() if r["站点键"] == "站-河东"]


def _现行轨序() -> list[str]:
    """现行入栏缓冲按观测时序给出的报文序。"""
    conn = 连接()
    try:
        return [
            r["报文编号"]
            for r in conn.execute(
                "SELECT 报文编号 FROM 入栏缓冲 WHERE 站点键=? ORDER BY 观测序",
                ("站-河东",),
            ).fetchall()
        ]
    finally:
        conn.close()


def test_双写两轨读引用不同():
    from app.services import 影子序

    # 逆序到达：先晚后早
    装载.装一批({"批次编号": "轨-1", "报文": [_报文("Y-late", "2026-11-24T08:40:00Z", 40.0)]})
    装载.装一批({"批次编号": "轨-2", "报文": [_报文("Y-early", "2026-11-24T08:10:00Z", 20.0)]})

    影子 = _影子轨序()
    现行 = _现行轨序()
    # 两轨都含这两笔，但读引用（排序依据）不同：影子按到达、现行按观测时
    assert set(影子) == {"Y-late", "Y-early"}
    assert 影子 == ["Y-late", "Y-early"]
    assert 现行 == ["Y-early", "Y-late"]
    assert 影子 != 现行

    档 = 影子序.归档列表()
    笔 = [r for r in 档 if r["报文编号"] in ("Y-late", "Y-early")]
    assert 笔[0]["到达序"] < 笔[1]["到达序"]
    assert 笔[0]["观测时"] == "2026-11-24T08:40:00Z"


def test_汇总物化带观测序首尾与指纹():
    装载.装一批({"批次编号": "汇-1", "报文": [_报文("M-late", "2026-11-24T09:40:00Z", 40.0)]})
    装载.装一批({"批次编号": "汇-2", "报文": [_报文("M-early", "2026-11-24T09:10:00Z", 20.0)]})
    报告 = 结栏.结当前栏()
    assert 报告["汇总数"] >= 1

    conn = 连接()
    try:
        r = conn.execute(
            "SELECT * FROM 站点汇总账 WHERE 站点键=? AND 指标键='PM25' ORDER BY 物化时 DESC LIMIT 1",
            ("站-河东",),
        ).fetchone()
    finally:
        conn.close()
    assert r is not None
    assert r["首观测时"] == "2026-11-24T09:10:00Z"
    assert r["末观测时"] == "2026-11-24T09:40:00Z"
    # 序指纹：物化时按观测序钉死的报文序
    assert "M-early" in r["序指纹"]
    assert r["序指纹"].index("M-early") < r["序指纹"].index("M-late")


def test_序拧花不得只凭笔数亮对齐():
    装载.装一批({"批次编号": "拧-1", "报文": [_报文("T-late", "2026-11-24T10:40:00Z", 40.0)]})
    装载.装一批({"批次编号": "拧-2", "报文": [_报文("T-early", "2026-11-24T10:10:00Z", 20.0)]})
    结栏.结当前栏()

    # 正常态：笔数对齐且序对齐
    果 = 贯验.跑一次()
    assert 果["是否对齐"] is True
    assert 果["序对齐"] is True
    对账 = [r for r in 贯验.序对账() if r["站点键"] == "站-河东"]
    assert 对账 and all(r["序对齐"] for r in 对账)

    # 注入拧花：只改影子归档的观测时（现行缓冲/汇总账不动），笔数仍然对得上
    conn = 连接()
    try:
        conn.execute(
            "UPDATE 收到序归档 SET 观测时='2026-11-24T10:59:00Z' WHERE 报文编号='T-early'"
        )
        conn.commit()
    finally:
        conn.close()

    跑 = 贯验.跑一次()
    # 笔数口径仍亮对齐……
    assert 跑["是否对齐"] is True
    # ……但序口径必须判撕裂，禁止拧花却亮对齐
    assert 跑["序对齐"] is False
    对账2 = [r for r in 贯验.序对账() if r["站点键"] == "站-河东"]
    坏 = [r for r in 对账2 if not r["序对齐"]]
    assert 坏, "影子序与现行缓冲序拧花时须能逐站点指出"
