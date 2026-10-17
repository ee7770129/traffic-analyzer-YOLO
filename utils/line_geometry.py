# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：計數線幾何運算工具
功能說明：
    提供「越線計數」所需的純幾何函式：
        1. 由邊界框取出代表點（中心或底邊中點）。
        2. 判定一個點位於計數線的哪一側。
        3. 判定車輛前後兩幀的位移線段是否跨越計數線，以及跨越方向。

    以「線段相交」判定跨越，而非「點是否落在區域內」，
    因此在低幀率串流（車輛每幀位移很大）下也不會漏判。

建立日期：2026-10-08
版本號：v1.2.0
"""

from typing import Optional

# 計數線的兩種通過方向
DIRECTION_IN = "進入"    # 由路口外側越線進入路口
DIRECTION_OUT = "離開"   # 由路口內側越線離開路口

ANCHOR_CENTER = "center"
ANCHOR_BOTTOM_CENTER = "bottom_center"


def anchor_point(xyxy, mode: str = ANCHOR_BOTTOM_CENTER) -> tuple:
    """
    取邊界框的代表點。

    斜角拍攝時，邊界框中心會隨車身高度往畫面上方偏移；
    底邊中點較接近車輛實際接觸地面的位置，故為預設值。
    """
    center_x = (xyxy[0] + xyxy[2]) / 2.0
    if mode == ANCHOR_CENTER:
        return (center_x, (xyxy[1] + xyxy[3]) / 2.0)
    return (center_x, float(xyxy[3]))


def side_of_line(point, line_start, line_end) -> float:
    """
    回傳點相對於有向線段的側別（外積）。
    正負號代表位於線的哪一側，0 代表剛好在線上。
    """
    return (
        (line_end[0] - line_start[0]) * (point[1] - line_start[1])
        - (line_end[1] - line_start[1]) * (point[0] - line_start[0])
    )


def segments_intersect(p1, p2, q1, q2) -> bool:
    """判定線段 p1-p2 與線段 q1-q2 是否相交（端點剛好接觸不算）。"""
    d1 = side_of_line(p1, q1, q2)
    d2 = side_of_line(p2, q1, q2)
    d3 = side_of_line(q1, p1, p2)
    d4 = side_of_line(q2, p1, p2)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def crossing_direction(previous, current, line_start, line_end, inside_point) -> Optional[str]:
    """
    判定車輛由 previous 移動到 current 時是否跨越計數線。

    參數：
        previous:     上一幀的代表點
        current:      本幀的代表點
        line_start:   計數線端點一
        line_end:     計數線端點二
        inside_point: 位於「路口內側」的任一參考點（通常取路口中心）

    回傳：
        "進入"／"離開"；未跨越則為 None。
    """
    if not segments_intersect(previous, current, line_start, line_end):
        return None

    inside_side = side_of_line(inside_point, line_start, line_end)
    current_side = side_of_line(current, line_start, line_end)

    # 參考點剛好落在線上時無法定義內外側，視為設定錯誤，不計數
    if inside_side == 0:
        return None

    return DIRECTION_IN if (inside_side * current_side > 0) else DIRECTION_OUT
