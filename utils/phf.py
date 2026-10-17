# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：尖峰小時係數（PHF）計算
功能說明：
    由車輛通過時間的序列，找出流量最大的連續一小時（尖峰小時），
    並計算尖峰小時係數：

        PHF = 尖峰小時流量 ÷ (4 × 尖峰小時內最大的 15 分鐘流量)

    PHF 介於 0.25 與 1.0 之間，越接近 1 代表該小時內車流越均勻，
    越低代表車流集中在某一個 15 分鐘內。

    觀測長度不足一小時時無法定義尖峰小時，回傳 None，
    由呼叫端決定如何呈現，不以外插值充數。

建立日期：2026-10-08
版本號：v1.2.0
"""

from typing import Optional


def bin_counts(timestamps: list, period_secs: float, duration_secs: float) -> list:
    """
    把事件時間依固定區間彙總為各區間的事件數。

    只保留「完整」的區間：尾端不足一個區間的零頭捨去，
    否則不完整區間的流量會被低估而拉低結果。
    """
    if period_secs <= 0:
        return []

    full_periods = int(duration_secs // period_secs)
    counts = [0] * full_periods
    for timestamp in timestamps:
        index = int(timestamp // period_secs)
        if 0 <= index < full_periods:
            counts[index] += 1
    return counts


def compute_phf(
    timestamps: list,
    duration_secs: float,
    period_secs: float = 900.0,
    periods_per_hour: int = 4,
) -> Optional[dict]:
    """
    計算尖峰小時係數。

    參數：
        timestamps:       每台車的通過時間（自影像起算的秒數）
        duration_secs:    觀測總長度（秒）
        period_secs:      子區間長度，交通工程慣用 900 秒（15 分鐘）
        periods_per_hour: 一小時內的子區間數，與 period_secs 對應

    回傳：
        觀測不足一小時、或尖峰小時內沒有車時回傳 None；否則回傳
        {"尖峰起始_秒", "尖峰小時流量", "最大區間流量", "PHF", "各區間流量"}
    """
    counts = bin_counts(timestamps, period_secs, duration_secs)
    if len(counts) < periods_per_hour:
        return None

    # 以子區間為步長滑動，找出流量最大的連續一小時
    best_start = 0
    best_volume = -1
    for start in range(len(counts) - periods_per_hour + 1):
        volume = sum(counts[start:start + periods_per_hour])
        if volume > best_volume:
            best_volume = volume
            best_start = start

    peak_counts = counts[best_start:best_start + periods_per_hour]
    peak_period = max(peak_counts)
    if peak_period <= 0:
        return None

    return {
        "尖峰起始_秒": best_start * period_secs,
        "尖峰小時流量": best_volume,
        "最大區間流量": peak_period,
        "PHF": round(best_volume / (periods_per_hour * peak_period), 3),
        "各區間流量": counts,
    }
