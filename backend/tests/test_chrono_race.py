"""争用失败测：乱序批撞上结栏缺互斥会排出双序。

- 重排途中结栏并发，双请求不得排出双序（同笔被物化两次/观测序撞号）。
- 缺锁时：SQLite 写冲突抛错或两条结栏各吃一遍在栏缓冲 → 双成功、双序。
"""
from __future__ import annotations

import threading

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


def _并发双路(甲, 乙) -> tuple[list, list]:
    屏障 = threading.Barrier(2)
    果甲: list = []
    果乙: list = []
    错: list = []

    def 跑(fn, 果):
        try:
            屏障.wait(timeout=10)
            果.append(fn())
        except Exception as e:  # noqa: BLE001 - 争用下任何异常都算失败证据
            错.append(f"{type(e).__name__}: {e}")

    t1 = threading.Thread(target=跑, args=(甲, 果甲))
    t2 = threading.Thread(target=跑, args=(乙, 果乙))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert not 错, f"并发写出现异常（缺互斥）：{错}"
    return 果甲, 果乙


def _库态() -> dict:
    conn = 连接()
    try:
        return {
            "在栏": conn.execute(
                "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
            ).fetchone()["c"],
            "已汇总缓冲": conn.execute(
                "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
            ).fetchone()["c"],
            "汇总账报文数": conn.execute(
                "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
            ).fetchone()["c"],
            "重复计入": conn.execute(
                """SELECT COUNT(*) AS c FROM (
                       SELECT 报文编号 FROM 入栏缓冲 WHERE 命运='已汇总'
                       GROUP BY 报文编号 HAVING COUNT(*) > 1
                   )"""
            ).fetchone()["c"],
            "观测序撞号": conn.execute(
                """SELECT COUNT(*) AS c FROM (
                       SELECT 站点键,指标键,观测序,COUNT(*) AS n FROM 入栏缓冲
                       GROUP BY 站点键,指标键,观测序 HAVING n > 1
                   )"""
            ).fetchone()["c"],
            "结栏赢批": conn.execute(
                "SELECT COUNT(*) AS c FROM 结栏批次 WHERE 汇总数 > 0"
            ).fetchone()["c"],
        }
    finally:
        conn.close()


def test_并发双结栏请求不得双序():
    # 逆序到达两笔先入栏
    装载.装一批({"批次编号": "争-1", "报文": [_报文("R-late", "2026-11-24T08:40:00Z", 40.0)]})
    装载.装一批({"批次编号": "争-2", "报文": [_报文("R-early", "2026-11-24T08:10:00Z", 20.0)]})

    果甲, 果乙 = _并发双路(结栏.结当前栏, 结栏.结当前栏)
    assert len(果甲) == 1 and len(果乙) == 1

    # 恰好一个请求物化、另一个空栏；不得双成功
    赢 = [r for r in (果甲[0], 果乙[0]) if r["汇总数"] > 0]
    空 = [r for r in (果甲[0], 果乙[0]) if r["空栏"]]
    assert len(赢) == 1
    assert len(空) == 1

    态 = _库态()
    assert 态["在栏"] == 0
    assert 态["已汇总缓冲"] == 2
    assert 态["汇总账报文数"] == 2          # 每笔只物化一次
    assert 态["重复计入"] == 0
    assert 态["观测序撞号"] == 0
    assert 态["结栏赢批"] == 1
    assert 贯验.跑一次()["是否对齐"] is True


def test_重排装载与结栏并发不排双序():
    # 栏内先放一笔，制造“重排途中撞上结栏”的交错窗口；多轮放大争用
    装载.装一批({"批次编号": "种", "报文": [_报文("R-seed", "2026-11-24T07:00:00Z", 10.0)]})

    def 逆序装载():
        # 单批内逆序，装载内部也要完成观测序重排
        return 装载.装一批({"批次编号": "争载", "报文": [
            _报文("R-x-late", "2026-11-24T07:40:00Z", 40.0),
            _报文("R-x-early", "2026-11-24T07:10:00Z", 20.0),
        ]})

    for _ in range(5):
        _并发双路(逆序装载, 结栏.结当前栏)

    态 = _库态()
    # 重排与结栏互斥：任何一笔缓冲只允许一条观测序、只被物化一次
    assert 态["观测序撞号"] == 0
    assert 态["重复计入"] == 0
    assert 态["汇总账报文数"] == 态["已汇总缓冲"]

    conn = 连接()
    try:
        rows = conn.execute(
            "SELECT 报文编号,观测序 FROM 入栏缓冲 WHERE 站点键='站-河东' ORDER BY 观测序"
        ).fetchall()
    finally:
        conn.close()
    序 = [r["观测序"] for r in rows]
    assert 序 == sorted(序) and len(set(序)) == len(序)
    assert 贯验.跑一次()["是否对齐"] is True
