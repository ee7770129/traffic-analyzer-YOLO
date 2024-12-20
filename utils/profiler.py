# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：效能計時器（profiler）
功能說明：
    提供裝飾器 `profile_time`，量測流水線各節點 `process()` 的耗時，
    以 DEBUG 等級寫入日誌。啟動時加上 `hydra.job_logging.root.level=DEBUG`
    即可觀察瓶頸落在哪一個節點。

建立日期：2024-12-18
版本號：v1.0.0
"""

import functools
import logging
import time

logger = logging.getLogger("profile")


def profile_time(func):
    """量測被裝飾方法的執行時間，並以 DEBUG 等級輸出（毫秒）。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        # args[0] 為節點實例本身，用來標示是哪一個節點花了多少時間
        owner = args[0].__class__.__name__ if args else "unknown"
        logger.debug("%s.%s 耗時 %.2f 毫秒", owner, func.__name__, elapsed_ms)

        return result

    return wrapper
