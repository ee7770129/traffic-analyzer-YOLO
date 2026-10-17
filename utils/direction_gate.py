# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：進入方向判定
功能說明：
    修正「第一個踩到的區域就算進入道路」在即時影像上的誤判。

    問題情境：
        車輛由近端道路右轉，因為離鏡頭近、移動快，常常等它已經開進
        另一條路的區域才第一次被偵測到。原規則會把那條路記成「進入道路」，
        但這台車其實正要從那條路離開。

    作法：
        車輛第一次出現在某個區域時先不下結論，等它移動一小段距離後，
        比較它與路口中心的距離變化：
            越來越近 → 朝路口內行駛 → 該區域為「進入道路」
            越來越遠 → 朝路口外行駛 → 該區域為「離開道路」，進入道路未知
        停等中的車輛沒有位移，會一直等到起步後才判定。

    本模組不匯入 core，只呼叫傳入軌跡物件的 observe_zone() 與 mark_exit_only()。

建立日期：2026-10-08
版本號：v1.2.0
"""

import math

from utils.geometry import bbox_center


class DirectionGate:
    """依行進方向決定車輛的第一個區域是進入還是離開。"""

    def __init__(self, inside_point, min_move_px: float) -> None:
        """
        參數：
            inside_point: 路口內側的參考點（通常取路口中心）
            min_move_px:  判定方向前車輛至少要移動的像素距離，
                          用來濾除邊界框抖動造成的假位移
        """
        self.inside_point = (float(inside_point[0]), float(inside_point[1]))
        self.min_move_px = float(min_move_px)

        self._probes: dict = {}      # {追蹤編號: {"zone", "point", "time"}} 尚未判定的軌跡
        self._decided: set = set()   # 已完成判定的追蹤編號

    def observe(self, track, zone_id, xyxy, timestamp: float) -> None:
        """
        取代直接呼叫 track.observe_zone()：先判定方向，再記錄區域。

        參數：
            track:     軌跡物件
            zone_id:   本幀所在區域編號，不在任何區域內時為 None
            xyxy:      本幀的邊界框
            timestamp: 本幀時間（秒）
        """
        track_id = track.track_id

        if track_id in self._decided:
            track.observe_zone(zone_id, timestamp)
            return

        point = bbox_center(xyxy)
        probe = self._probes.get(track_id)

        if probe is None:
            # 還沒踩到任何區域：沒有需要判定的東西
            if zone_id is not None:
                self._probes[track_id] = {"zone": zone_id, "point": point, "time": timestamp}
            return

        moved = math.dist(point, probe["point"])
        if moved < self.min_move_px:
            return

        start_distance = math.dist(probe["point"], self.inside_point)
        current_distance = math.dist(point, self.inside_point)

        if current_distance < start_distance:
            # 朝路口內行駛：以第一次出現的時間補記進入，再處理本幀所在的區域
            track.observe_zone(probe["zone"], probe["time"])
            track.observe_zone(zone_id, timestamp)
        else:
            track.mark_exit_only(probe["zone"], probe["time"])

        self._decided.add(track_id)
        del self._probes[track_id]

    def forget(self, track_id: int) -> None:
        """軌跡離場後清除其判定狀態，避免長時間執行時持續累積。"""
        self._probes.pop(track_id, None)
        self._decided.discard(track_id)
