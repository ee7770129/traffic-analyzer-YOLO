# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：畫面繪製節點
功能說明：
    將分析結果視覺化，產出帶有疊加圖層的成果影格：

        1. 道路區域多邊形，以各道路代表色標示並標註編號。
        2. 車輛邊界框，顏色代表該車「從哪一條路進入」，未判定者以灰色顯示。
        3. 車輛標籤，顯示追蹤編號與中文車種。
        4. 右側統計面板，顯示累計車次、PCU、各道路流量與車種組成。

    繪製策略：圖形以 cv2 完成（速度快），所有中文字集中交由 TextDrawer
    一次繪製，避免重複進行影像格式轉換。

建立日期：2025-02-14
版本號：v1.0.0
"""

import logging

import cv2
import numpy as np

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from utils.fps_counter import FPSCounter
from utils.profiler import profile_time
from utils.text_drawer import TextDrawer

logger = logging.getLogger(__name__)

# 未判定進入道路時使用的中性色（BGR）
_UNKNOWN_COLOR = (160, 160, 160)


class RenderNode:
    """分析結果視覺化。"""

    def __init__(self, config: dict) -> None:
        """
        參數：
            config: 完整設定檔，使用 render_node 與 general 區段。
        """
        render_cfg = config["render_node"]
        general_cfg = config["general"]

        self.show_roi = bool(render_cfg["show_roi"])
        self.show_labels = bool(render_cfg["show_labels"])
        self.show_panel = bool(render_cfg["show_panel"])
        self.draw_fps = bool(render_cfg["draw_fps"])
        self.panel_width = int(render_cfg["panel_width"])
        self.box_thickness = int(render_cfg["box_thickness"])

        self.text_drawer = TextDrawer(
            font_candidates=list(render_cfg["font_candidates"]),
            sizes=dict(render_cfg["font_sizes"]),
        )
        self.fps_counter = FPSCounter(int(render_cfg["fps_window_frames"]))

        # 道路代表色（設定檔以 BGR 提供）
        self.road_colors = {
            int(key): tuple(int(c) for c in value)
            for key, value in general_cfg["colors_of_roads"].items()
        }

        self._polygon_cache: dict = {}  # 多邊形頂點陣列，首幀建立後重複使用

    @profile_time
    def process(self, element):
        """產生疊加圖層後的成果影格，寫入 element.frame_result。"""
        if isinstance(element, StreamEndElement):
            return element

        assert isinstance(element, FrameElement), (
            f"RenderNode｜輸入型別錯誤：{type(element)}"
        )

        canvas = element.frame.copy()
        text_items = []

        if self.show_roi:
            self._draw_roads(canvas, element.roads_info, text_items)

        self._draw_vehicles(canvas, element, text_items)

        if self.show_panel:
            canvas = self._attach_panel(canvas, element, text_items)

        if self.draw_fps:
            fps = self.fps_counter.update()
            text_items.append(
                {
                    "text": f"處理速度 {fps:5.1f} FPS",
                    "xy": (10, 8),
                    "color": (255, 255, 255),
                    "size": "normal",
                    "bg": (0, 0, 0),
                    "padding": 4,
                }
            )

        element.frame_result = self.text_drawer.draw(canvas, text_items)
        return element

    # ------------------------------------------------------------------
    # 圖形繪製
    # ------------------------------------------------------------------
    def _draw_roads(self, canvas: np.ndarray, roads_info: dict, text_items: list) -> None:
        """繪製各道路區域的多邊形輪廓，並在區域中心標註道路編號。"""
        if not self._polygon_cache:
            for key, flat in roads_info.items():
                points = np.array(
                    [[int(flat[i]), int(flat[i + 1])] for i in range(0, len(flat) - 1, 2)],
                    dtype=np.int32,
                )
                if len(points) >= 3:
                    self._polygon_cache[int(key)] = points

        for road_id, points in self._polygon_cache.items():
            color = self.road_colors.get(road_id, _UNKNOWN_COLOR)
            cv2.polylines(canvas, [points], isClosed=True, color=color, thickness=2)

            # 以頂點平均值作為區域中心，標註道路編號讓畫面與報表可對照
            center = points.mean(axis=0).astype(int)
            text_items.append(
                {
                    "text": f"道路{road_id}",
                    "xy": (int(center[0]) - 26, int(center[1]) - 12),
                    "color": (0, 0, 0),
                    "size": "small",
                    "bg": color,
                    "padding": 3,
                }
            )

    def _draw_vehicles(self, canvas: np.ndarray, element, text_items: list) -> None:
        """繪製車輛邊界框，並把標籤文字加入待繪製清單。"""
        for index, track_id in enumerate(element.tracked_ids):
            xyxy = element.tracked_xyxy[index]
            track = element.active_tracks.get(track_id)

            # 邊界框顏色代表該車的進入道路，未判定時為灰色
            entry_road = track.entry_road if track is not None else None
            color = self.road_colors.get(entry_road, _UNKNOWN_COLOR)

            x1, y1, x2, y2 = (int(v) for v in xyxy[:4])
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, self.box_thickness)

            if not self.show_labels:
                continue

            vehicle_type = track.vehicle_type if track is not None else None
            label = f"{track_id} {vehicle_type}" if vehicle_type else f"{track_id}"

            # 標籤畫在框上方；太靠近畫面頂端時改畫在框內
            label_y = y1 - 22 if y1 - 22 > 0 else y1 + 2
            text_items.append(
                {
                    "text": label,
                    "xy": (x1, label_y),
                    "color": (255, 255, 255),
                    "size": "small",
                    "bg": color,
                    "padding": 2,
                }
            )

    # ------------------------------------------------------------------
    # 統計面板
    # ------------------------------------------------------------------
    def _attach_panel(self, canvas: np.ndarray, element, text_items: list) -> np.ndarray:
        """在畫面右側接上統計面板，並把面板文字加入待繪製清單。"""
        height = canvas.shape[0]
        panel = np.zeros((height, self.panel_width, 3), dtype=np.uint8)
        combined = np.hstack([canvas, panel])

        origin_x = canvas.shape[1]
        self._compose_panel_text(element, origin_x, height, text_items)

        return combined

    def _compose_panel_text(self, element, origin_x: int, height: int, text_items: list) -> None:
        """
        依統計資料排版面板文字。

        以 y 游標由上往下依序排版，超出面板高度即停止，避免文字溢出畫面。
        """
        stats = element.statistics or {}
        left = origin_x + 20
        indent = left + 16
        y = 18

        def add(text, size="normal", color=(255, 255, 255), x=None):
            """加入一行文字並回傳是否仍有版面空間。"""
            nonlocal y
            line_height = {"small": 22, "normal": 27, "large": 36}.get(size, 27)
            if y + line_height > height:
                return False
            text_items.append(
                {"text": text, "xy": (x if x is not None else left, y), "color": color, "size": size}
            )
            y += line_height
            return True

        add("路口車流分析", size="large", color=(120, 220, 255))
        y += 6

        # ---- 處理進度 ----
        if element.total_frames > 0:
            progress = element.frame_num / element.total_frames * 100
            add(f"處理進度　{progress:5.1f}％", size="small", color=(200, 200, 200))
        add(f"影片時間　{element.timestamp:6.1f} 秒", size="small", color=(200, 200, 200))
        add(f"畫面車輛　{stats.get('畫面車輛數', 0):4d} 輛", size="small", color=(200, 200, 200))
        y += 10

        # ---- 累計統計 ----
        add(f"累計車次　{stats.get('累計車次', 0):5d} 輛", color=(140, 255, 180))
        add(f"累計 PCU 　{stats.get('累計PCU', 0):7.1f}", color=(140, 255, 180))
        add(f"轉向紀錄　{stats.get('轉向筆數', 0):5d} 筆", color=(140, 255, 180))
        y += 12

        # ---- 各道路 ----
        window_secs = stats.get("流率視窗秒", 0)
        add(f"各道路進入量（近 {window_secs:.0f} 秒流率）", size="small", color=(180, 180, 255))
        road_totals = stats.get("各道路累計", {})
        road_rates = stats.get("各道路流率", {})
        for road in sorted(road_totals):
            color = self.road_colors.get(road, _UNKNOWN_COLOR)
            line = f"道路{road}　{road_totals[road]:4d} 輛　{road_rates.get(road, 0.0):5.1f} 輛/分"
            if not add(line, size="small", color=color, x=indent):
                return
        y += 12

        # ---- 車種組成 ----
        composition = stats.get("車種組成", {})
        if composition:
            add("車種組成", size="small", color=(180, 180, 255))
            total = sum(composition.values()) or 1
            for label, count in sorted(composition.items(), key=lambda kv: -kv[1]):
                line = f"{label}　{count:4d} 輛　{count / total * 100:4.1f}％"
                if not add(line, size="small", x=indent):
                    return
