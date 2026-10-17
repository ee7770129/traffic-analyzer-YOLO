# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：詳細資料面板
功能說明：
    繪製多路口畫面右側的詳細資料面板。每個路口一個區塊，高度與左側該路口的
    影像格相同，內容為：

        重點數字   累計車次、累計 PCU、畫面車輛、越線進入、越線離開、推估小時流量
        計數線     各計數線的進入與離開車次
        各道路     各道路的進入量與近期流率
        車種組成   各車種的車次與占比（橫條）
        每分鐘車流 最近數分鐘每分鐘新增的車次（直條）

    圖形一律使用單一色相表示數量大小，文字使用中性色，不以顏色區分類別。
    本模組只負責繪製，不持有狀態；每分鐘車流由呼叫端傳入。

建立日期：2026-10-09
版本號：v1.2.0
"""

import cv2
import numpy as np

# 深色面板的配色（BGR）
_SURFACE = (24, 24, 24)
_TILE = (42, 42, 42)
_RULE = (64, 64, 64)
_TEXT = (236, 236, 236)
_MUTED = (160, 160, 160)
_BAR = (214, 146, 62)        # 數量橫條與直條的單一色相
_BAR_CURRENT = (140, 110, 70)  # 尚未結束的那一分鐘以較淡的同色相表示

_PADDING = 18
_GAP = 2

# 表格數值欄的寬度（像素），表頭與資料列共用
_NARROW_COLUMNS = (70, 70)
_RATE_COLUMNS = (70, 150)


def format_elapsed(seconds: float) -> str:
    """把秒數格式化為「時:分:秒」或「分:秒」。"""
    total = int(max(seconds, 0))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def line_totals(statistics: dict) -> tuple:
    """回傳所有計數線加總的 (進入, 離開) 車次。"""
    lines = statistics.get("越線計數") or {}
    return (
        sum(info.get("進入", 0) for info in lines.values()),
        sum(info.get("離開", 0) for info in lines.values()),
    )


def composition_rows(statistics: dict) -> list:
    """回傳車種組成列 [(車種, 車次, 占比)]，依車次由多到少。"""
    composition = statistics.get("車種組成") or {}
    total = sum(composition.values())
    if total <= 0:
        return []
    return [
        (label, count, count / total)
        for label, count in sorted(composition.items(), key=lambda item: -item[1])
    ]


class DetailPanel:
    """多路口詳細資料面板的繪製器。"""

    def __init__(self, text_drawer, width: int, block_height: int) -> None:
        """
        參數：
            text_drawer:  已載入字型的 TextDrawer，需具備 small／normal／large／hero 四種字級
            width:        面板寬度（像素）
            block_height: 每個路口區塊的高度，須與左側影像格（含標題列）相同
        """
        self.text_drawer = text_drawer
        self.width = int(width)
        self.block_height = int(block_height)

    def render(self, blocks: list) -> np.ndarray:
        """
        繪製整張面板。

        參數：
            blocks: 每個路口一個 dict：
                    {"name", "status", "statistics", "elapsed_secs",
                     "per_minute"（每分鐘車次串列）, "hourly_rate"（或 None）}
        """
        canvas = np.full((self.block_height * max(len(blocks), 1), self.width, 3),
                         _SURFACE, dtype=np.uint8)
        text_items = []
        for index, block in enumerate(blocks):
            top = index * self.block_height
            self._draw_block(canvas, text_items, block, top)
            if index > 0:
                cv2.line(canvas, (0, top), (self.width, top), _RULE, 1)
        return self.text_drawer.draw(canvas, text_items)

    # ------------------------------------------------------------------
    # 區塊
    # ------------------------------------------------------------------
    def _draw_block(self, canvas, text_items, block: dict, top: int) -> None:
        statistics = block.get("statistics") or {}
        left, right = _PADDING, self.width - _PADDING

        self._text(text_items, block["name"], left, top + 10, "large")
        self._text_right(
            text_items,
            f"{block['status']}　已分析 {format_elapsed(block.get('elapsed_secs', 0))}",
            right, top + 18, "small", _MUTED,
        )

        entered, departed = line_totals(statistics)
        hourly = block.get("hourly_rate")
        tiles = [
            ("累計車次", str(statistics.get("累計車次", 0)), "輛"),
            ("累計 PCU", str(statistics.get("累計PCU", 0)), ""),
            ("畫面車輛", str(statistics.get("畫面車輛數", 0)), "輛"),
            ("越線進入", str(entered), "車次"),
            ("越線離開", str(departed), "車次"),
            ("推估小時流量", "—" if hourly is None else str(hourly), "輛/時"),
        ]
        tiles_top = top + 58
        tiles_height = 92
        self._draw_tiles(canvas, text_items, tiles, left, tiles_top, right - left, tiles_height)

        # 下半部分成三欄：計數線與各道路、車種組成、每分鐘車流
        body_top = tiles_top + tiles_height + 20
        body_bottom = top + self.block_height - _PADDING
        column_gap = 28
        column_width = (right - left - 2 * column_gap) // 3
        columns = [left + i * (column_width + column_gap) for i in range(3)]

        next_y = self._draw_lines_table(text_items, canvas, statistics, columns[0], body_top, column_width)
        self._draw_roads_table(text_items, canvas, statistics, columns[0], next_y + 14, column_width)
        self._draw_composition(canvas, text_items, statistics, columns[1], body_top, column_width)
        self._draw_per_minute(canvas, text_items, block.get("per_minute") or [],
                              columns[2], body_top, column_width, body_bottom,
                              int(block.get("history_slots", 0)))

    def _draw_tiles(self, canvas, text_items, tiles, left, top, width, height) -> None:
        tile_width = (width - _GAP * 4 * (len(tiles) - 1)) // len(tiles)
        for index, (label, value, unit) in enumerate(tiles):
            x = left + index * (tile_width + _GAP * 4)
            cv2.rectangle(canvas, (x, top), (x + tile_width, top + height), _TILE, -1)
            self._text(text_items, label, x + 12, top + 10, "small", _MUTED)
            self._text(text_items, value, x + 12, top + 38, "hero")
            if unit:
                value_width = self.text_drawer.text_size(value, "hero")[0]
                self._text(text_items, unit, x + 18 + value_width, top + 56, "small", _MUTED)

    def _draw_lines_table(self, text_items, canvas, statistics, left, top, width) -> int:
        """繪製計數線表格，回傳表格底端的 y 座標。"""
        self._section_title(text_items, canvas, "計數線", left, top, width,
                            ["進入", "離開"], _NARROW_COLUMNS)
        lines = statistics.get("越線計數") or {}
        y = top + 36
        if not lines:
            self._text(text_items, "未設定計數線", left, y, "small", _MUTED)
            return y + 26
        for line_id in sorted(lines):
            info = lines[line_id]
            self._table_row(text_items, info.get("名稱", str(line_id)), left, y, width,
                            [str(info.get("進入", 0)), str(info.get("離開", 0))], _NARROW_COLUMNS)
            y += 28
        return y

    def _draw_roads_table(self, text_items, canvas, statistics, left, top, width) -> None:
        window = int(statistics.get("流率視窗秒", 0) or 0)
        self._section_title(text_items, canvas, "各道路進入量", left, top, width,
                            ["累計", f"近{window}秒 輛/分"], _RATE_COLUMNS)
        totals = statistics.get("各道路累計") or {}
        rates = statistics.get("各道路流率") or {}
        y = top + 36
        for road in sorted(totals):
            self._table_row(text_items, f"道路 {road}", left, y, width,
                            [str(totals[road]), f"{rates.get(road, 0.0):.1f}"], _RATE_COLUMNS)
            y += 28

    def _draw_composition(self, canvas, text_items, statistics, left, top, width) -> None:
        self._section_title(text_items, canvas, "車種組成", left, top, width)
        rows = composition_rows(statistics)
        y = top + 36
        if not rows:
            self._text(text_items, "尚無資料", left, y, "small", _MUTED)
            return

        label_width = 84
        value_width = 104
        bar_left = left + label_width
        bar_span = max(width - label_width - value_width, 10)
        largest = rows[0][1]
        for label, count, share in rows:
            self._text(text_items, label, left, y, "small")
            bar_length = max(int(bar_span * count / largest), 2)
            cv2.rectangle(canvas, (bar_left, y + 6), (bar_left + bar_length, y + 18), _BAR, -1)
            self._text_right(text_items, f"{count} 輛　{share * 100:.0f}%",
                             left + width, y, "small", _MUTED)
            y += 30

    def _draw_per_minute(self, canvas, text_items, per_minute, left, top, width, bottom,
                         slots: int = 0) -> None:
        self._section_title(text_items, canvas, "每分鐘車流（輛）", left, top, width)
        chart_top = top + 60
        chart_bottom = bottom - 26
        if not per_minute or chart_bottom <= chart_top:
            self._text(text_items, "尚無資料", left, top + 36, "small", _MUTED)
            return

        # 一律保留完整的欄位數並靠右排列：剛開始分析時直條不會被撐得很寬，
        # 之後每過一分鐘也只是多一根直條，既有直條的位置與寬度不變
        count = len(per_minute)
        slots = max(int(slots), count)
        slot = width / slots
        offset = slots - count
        bar_width = max(int(slot) - _GAP * 2, 3)
        largest = max(max(per_minute), 1)
        peak_index = per_minute.index(max(per_minute))

        cv2.line(canvas, (left, chart_bottom), (left + width, chart_bottom), _RULE, 1)
        for index, value in enumerate(per_minute):
            x = int(left + (offset + index) * slot) + _GAP
            height = int((chart_bottom - chart_top) * value / largest)
            is_current = index == count - 1
            if height > 0:
                cv2.rectangle(canvas, (x, chart_bottom - height), (x + bar_width, chart_bottom - 1),
                              _BAR_CURRENT if is_current else _BAR, -1)
            # 只標示最高的一分鐘與目前這一分鐘，避免每根直條都擠著數字
            if index in (peak_index, count - 1):
                text = str(value)
                text_width = self.text_drawer.text_size(text, "small")[0]
                self._text(text_items, text, x + (bar_width - text_width) // 2,
                           chart_bottom - height - 24, "small")

        self._text(text_items, f"{slots - 1} 分鐘前", left, chart_bottom + 6, "small", _MUTED)
        self._text_right(text_items, "現在（未滿一分鐘）", left + width, chart_bottom + 6, "small", _MUTED)

    # ------------------------------------------------------------------
    # 文字與表格的共用繪製
    # ------------------------------------------------------------------
    def _section_title(self, text_items, canvas, title, left, top, width,
                       headers=(), column_widths=()) -> None:
        """繪製小節標題；headers 為靠右對齊的數值欄表頭，column_widths 為各欄寬度。"""
        self._text(text_items, title, left, top, "normal")
        self._right_aligned_cells(text_items, headers, column_widths, left + width, top + 4, _MUTED)
        cv2.line(canvas, (left, top + 30), (left + width, top + 30), _RULE, 1)

    def _table_row(self, text_items, label, left, y, width, values, column_widths) -> None:
        """繪製一列資料；數值欄與表頭使用相同的欄寬，上下才會對齊。"""
        self._text(text_items, label, left, y, "small")
        self._right_aligned_cells(text_items, values, column_widths, left + width, y, _TEXT)

    def _right_aligned_cells(self, text_items, cells, column_widths, right, y, color) -> None:
        """由右至左排列各欄，每欄文字靠該欄右緣對齊。"""
        x = right
        for cell, column_width in zip(reversed(list(cells)), reversed(list(column_widths))):
            self._text_right(text_items, cell, x, y, "small", color)
            x -= column_width

    def _text(self, text_items, text, x, y, size="small", color=_TEXT) -> None:
        text_items.append({"text": text, "xy": (int(x), int(y)), "color": color, "size": size})

    def _text_right(self, text_items, text, right, y, size="small", color=_TEXT) -> None:
        width = self.text_drawer.text_size(text, size)[0]
        self._text(text_items, text, right - width, y, size, color)
