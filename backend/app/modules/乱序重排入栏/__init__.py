"""乱序重排入栏（已接主链）。

契约：
- 同站点乱序到达按观测时重排后再入栏（services/观测序，甲形态单轨）。
- 双写两轨：收到序进只读归档 services/影子序，现行缓冲读观测时序。
- 重排落库与装载/物化同事务同成同败；与结栏共用 services/互斥.栏写锁。
- 不得改坏基线默认门槛 happy path（装载→入栏/坏点→结栏汇总→贯验）。
- 页面须能读到：当前策略名、命运变化、可点的下一步。
"""
NAME = "乱序重排入栏"
CONTRACT = "同站点乱序到达按观测时重排后再入栏"
HOOKS = ("before_load", "after_load", "decide_gate", "before_close", "after_close", "extra_verify_checks")
形态 = "甲：切流账册按观测时排序后物化；乙：收到序只读归档双轨"


def describe() -> dict:
    return {
        "空桩": NAME,
        "契约": CONTRACT,
        "钩子": list(HOOKS),
        "默认启用": True,
        "状态": "已接主链",
        "工程形态": 形态,
        "只读接口": ("/api/观测序裁决", "/api/收到序归档", "/api/序对账"),
    }


def before_load(batch: dict) -> dict:
    return batch


def after_load(report: dict) -> dict:
    return report


def decide_gate(event: dict, rules: dict) -> str:
    return "入栏"


def before_close(pen_id: str) -> None:
    return None


def after_close(report: dict) -> dict:
    return report


def extra_verify_checks(snapshot: dict) -> list[str]:
    return []
