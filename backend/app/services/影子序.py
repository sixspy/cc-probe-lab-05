"""影子序（乙形态：双写两轨）。

- 收到序归档：报文装载即按到达序写一份只读影子，永不随重排改写。
- 现行轨：入栏缓冲按观测序读（见 services.观测序）。两轨读引用不同。
- 序对账：汇总账钉死的观测序指纹，须与影子归档里同组报文的观测时序一致；
  笔数对得上但序拧花，判序撕裂，不许只凭笔数亮对齐。
"""
from __future__ import annotations

from app.db import 连接
from app.services import 时间


def 下一到达序(conn, 站点键: str) -> int:
    r = conn.execute(
        "SELECT COUNT(*) AS c FROM 收到序归档 WHERE 站点键=?", (站点键,)
    ).fetchone()
    return int(r["c"])


def 归档写入(conn, ev: dict, 读数: float, 归档时: str) -> None:
    """装载同事务双写：观测报文 + 收到序归档（到达序）。"""
    序 = 下一到达序(conn, ev["站点键"])
    conn.execute(
        """INSERT INTO 收到序归档(报文编号,站点键,指标键,读数,观测时,到达序,归档时)
           VALUES (?,?,?,?,?,?,?)""",
        (ev["报文编号"], ev["站点键"], ev["指标键"], 读数, ev["观测时"], 序, 归档时),
    )


def 归档列表() -> list[dict]:
    """只读影子轨：按站点、到达序。"""
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 收到序归档 ORDER BY 站点键,到达序"
            ).fetchall()
        ]
    finally:
        conn.close()


def 序对账(conn=None) -> list[dict]:
    """逐汇总组对账：汇总账观测序指纹 vs 影子归档按观测时重排的序。"""
    自有 = conn is None
    if 自有:
        conn = 连接()
    try:
        汇总 = conn.execute("SELECT * FROM 站点汇总账").fetchall()
        出 = []
        for h in 汇总:
            指纹 = [s for s in (h["序指纹"] or "").split(",") if s]
            影子 = conn.execute(
                """SELECT 报文编号,观测时 FROM 收到序归档
                   WHERE 站点键=? AND 指标键=?
                   ORDER BY 观测时""",
                (h["站点键"], h["指标键"]),
            ).fetchall()
            影子观测序 = [r["报文编号"] for r in 影子]
            # 同组取交集，避免不同栏/批次的他笔污染比对
            影子组 = [i for i in 影子观测序 if i in set(指纹)]
            对齐 = 指纹 == 影子组 and len(指纹) == h["报文数"]
            出.append({
                "汇总编号": h["汇总编号"],
                "栏号": h["栏号"],
                "站点键": h["站点键"],
                "指标键": h["指标键"],
                "现行序": 指纹,
                "影子观测序": 影子组,
                "序对齐": 对齐,
            })
        return 出
    finally:
        if 自有:
            conn.close()


def 全局序对齐(conn=None) -> bool:
    return all(r["序对齐"] for r in 序对账(conn))
