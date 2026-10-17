# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：計數線繪製節點
功能說明：
    在 RenderNode 產出的成果影格上，加畫計數線與各線的即時進出車次。

    獨立成一個節點而不改動 RenderNode，是為了讓越線計數可以整組開關，
    停用時既有畫面完全不受影響。

建立日期：2026-10-08
版本號：v1.2.0
"""

import cv2

from core.stream_end_element import StreamEndElement
from utils.profiler import profile_time
from utils.text_drawer import TextDrawer


class LineRenderNode:
    """計數線與越線車次的疊加繪製。"""

    def __init__(self, config: dict, lines: dict) -> None:
        """
        參數：
            config: 完整設定檔，使用 render_node 的字型設定與 line_counting 的顏色設定。
            lines:  LineCountingNode.lines，{線編號: {"name", "p1", "p2"}}。
        """
        render_cfg = config["render_node"]
        line_cfg = config["line_counting"]

        self.lines = lines
        self.color = tuple(int(c) for c in line_cfg["line_color"])
        self.thickness = int(line_cfg["line_thickness"])

        self.text_drawer = TextDrawer(
            font_candidates=list(render_cfg["font_candidates"]),
            sizes=dict(render_cfg["font_sizes"]),
        )

    @profile_time
    def process(self, element):
        """在成果影格上加畫計數線；沒有成果影格時不處理。"""
        if isinstance(element, StreamEndElement) or element.frame_result is None:
            return element

        canvas = element.frame_result
        counts = element.statistics.get("越線計數") or {}
        text_items = []

        for line_id, line in self.lines.items():
            p1 = (int(line["p1"][0]), int(line["p1"][1]))
            p2 = (int(line["p2"][0]), int(line["p2"][1]))
            cv2.line(canvas, p1, p2, self.color, self.thickness, cv2.LINE_AA)

            info = counts.get(line_id, {"進入": 0, "離開": 0})
            text_items.append(
                {
                    "text": f"{line['name']}　進 {info['進入']}　出 {info['離開']}",
                    "xy": ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2),
                    "color": (255, 255, 255),
                    "size": "small",
                    "bg": (0, 0, 0),
                    "padding": 3,
                }
            )

        element.frame_result = self.text_drawer.draw(canvas, text_items)
        return element
