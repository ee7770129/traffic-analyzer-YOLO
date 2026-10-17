# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：lap 相容層（以 SciPy 實作的 lapjv）
功能說明：
    ByteTrack 以 lap.lapjv 求解追蹤框與偵測框的最佳配對。
    官方的 lap／lapx 套件內含編譯過的二進位檔，在啟用「應用程式控制原則」
    （例如 Windows 智慧型應用程式控制）的電腦上會被系統擋下而無法載入，
    導致整個分析無法執行。

    本檔與 cython_bbox.py 的作法相同：放在專案根目錄，匯入順序優先於
    已安裝的套件，以 SciPy 的 linear_sum_assignment 提供等價的 lapjv 介面，
    因此不需修改 vendor/ 內的第三方程式碼，也不必載入被擋下的檔案。

    只實作 ByteTrack 實際用到的呼叫方式：
        cost, x, y = lap.lapjv(cost_matrix, extend_cost=True, cost_limit=thresh)

建立日期：2026-10-08
版本號：v1.2.0
"""

import numpy as np
from scipy.optimize import linear_sum_assignment

__version__ = "compat-scipy-1.0"


def lapjv(cost_matrix, extend_cost: bool = False, cost_limit: float = np.inf, return_cost: bool = True):
    """
    求解線性指派問題。

    參數：
        cost_matrix: 形狀 (N, M) 的成本矩陣
        extend_cost: 是否允許非方陣（本相容層一律支援，參數僅為介面相容）
        cost_limit:  成本上限；配對成本高於此值者視為未配對

    回傳：
        (總成本, x, y)
        x[i] 為第 i 列配到的欄編號，未配對為 -1；
        y[j] 為第 j 欄配到的列編號，未配對為 -1。
    """
    cost = np.asarray(cost_matrix, dtype=np.float64)
    if cost.ndim != 2:
        raise ValueError("lapjv｜成本矩陣必須為二維陣列")

    n_rows, n_cols = cost.shape
    x = np.full(n_rows, -1, dtype=int)
    y = np.full(n_cols, -1, dtype=int)
    if n_rows == 0 or n_cols == 0:
        return (0.0, x, y) if return_cost else (x, y)

    if np.isfinite(cost_limit):
        # 與原套件相同的擴充方式：每一列、每一欄都可改配給成本為
        # cost_limit / 2 的虛擬對象，因此成本高於 cost_limit 的配對不會被選中
        size = n_rows + n_cols
        extended = np.full((size, size), cost_limit / 2.0, dtype=np.float64)
        extended[n_rows:, n_cols:] = 0.0
        extended[:n_rows, :n_cols] = cost
    else:
        extended = cost

    row_indices, col_indices = linear_sum_assignment(extended)

    total = 0.0
    for row, col in zip(row_indices, col_indices):
        if row < n_rows and col < n_cols:
            x[row] = col
            y[col] = row
            total += cost[row, col]

    return (total, x, y) if return_cost else (x, y)
