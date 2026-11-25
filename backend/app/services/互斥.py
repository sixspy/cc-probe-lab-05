"""栏内编排互斥。

乱序重排（装载写缓冲）与结栏物化共用同一把进程内写锁：
- 重排途中撞上结栏，二者串行，不会排出双序或双成功。
- 锁只护“栏内编排”写段；只读接口不取锁。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

# 装载重排 ↔ 结栏物化 的同一把互斥
栏写锁 = threading.RLock()


@contextmanager
def 栏写互斥():
    栏写锁.acquire()
    try:
        yield
    finally:
        栏写锁.release()
