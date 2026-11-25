"""观测序裁决（甲形态：单轨，切流账册按观测时排序后物化）。

- 入栏写入前先按观测时重排：同站点+指标的在栏缓冲以观测序 0..n 钉死，
  到达序保留灌入先后，两序可分开看。
- 重排落库与缓冲写入同一连接同一事务，同成同败。
- 只读裁决接口：站点键、首观测时、形态标记。
"""
from __future__ import annotations

from app.services import 时间

形态_乱序 = "乱序重排"
形态_正序 = "正序"


def 下一到达序(conn, 站点键: str) -> int:
    """站点内单调的到达序：该站已入栏缓冲笔数（不随重排改变）。"""
    r = conn.execute(
        "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 站点键=?", (站点键,)
    ).fetchone()
    return int(r["c"])


def 下一观测序(conn, 站点键: str, 指标键: str) -> int:
    """站点+指标全组（含已物化行）的下一观测序，保证跨结栏不撞号。"""
    r = conn.execute(
        "SELECT COALESCE(MAX(观测序),-1)+1 AS n FROM 入栏缓冲 WHERE 站点键=? AND 指标键=?",
        (站点键, 指标键),
    ).fetchone()
    return int(r["n"])


def 重排站点指标(conn, 站点键: str, 指标键: str) -> None:
    """在栏行按观测时重排；观测序在全组（含已物化行）内保持唯一不撞号。

    已物化行的序冻结不参与重排，在栏行取全组最大序之后再按观测时排。
    """
    已物化 = conn.execute(
        """SELECT COALESCE(MAX(观测序),-1) AS m FROM 入栏缓冲
           WHERE 站点键=? AND 指标键=? AND 命运!='在栏'""",
        (站点键, 指标键),
    ).fetchone()["m"]
    基线 = int(已物化) + 1
    rows = conn.execute(
        """SELECT 报文编号,观测时 FROM 入栏缓冲
           WHERE 站点键=? AND 指标键=? AND 命运='在栏'""",
        (站点键, 指标键),
    ).fetchall()
    序表 = sorted(rows, key=lambda r: (时间.观测序排序键(r["观测时"]), r["报文编号"]))
    for i, r in enumerate(序表):
        conn.execute(
            "UPDATE 入栏缓冲 SET 观测序=? WHERE 报文编号=?",
            (基线 + i, r["报文编号"]),
        )


def _形态(rows: list) -> str:
    """到达序与观测序不一致即发生过乱序重排。"""
    by_观测 = sorted(rows, key=lambda r: r["观测序"])
    到达 = [r["到达序"] for r in by_观测]
    return 形态_乱序 if 到达 != sorted(到达) else 形态_正序


def 裁决(conn=None) -> list[dict]:
    """只读：按站点+指标给出首观测时与形态标记。"""
    自有 = conn is None
    if 自有:
        from app.db import 连接
        conn = 连接()
    try:
        groups: dict[tuple[str, str], list] = {}
        rows = conn.execute(
            """SELECT 站点键,指标键,报文编号,观测时,到达序,观测序
               FROM 入栏缓冲 WHERE 命运='在栏'"""
        ).fetchall()
        for r in rows:
            groups.setdefault((r["站点键"], r["指标键"]), []).append(dict(r))
        out = []
        for (站点, 指标), evs in sorted(groups.items()):
            按观测 = sorted(evs, key=lambda r: r["观测序"])
            out.append({
                "站点键": 站点,
                "指标键": 指标,
                "首观测时": 按观测[0]["观测时"],
                "末观测时": 按观测[-1]["观测时"],
                "在栏笔数": len(evs),
                "形态标记": _形态(evs),
            })
        return out
    finally:
        if 自有:
            conn.close()
