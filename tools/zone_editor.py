# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：道路區域座標編輯工具
功能說明：
    以滑鼠在影片的任一影格上直接框選各條聯絡道的偵測區域，
    存成 configs/roads_polygons.json，取代手動填寫座標數字。

    換一支新影片時，區域座標必須重畫，否則計數結果完全無意義。
    本工具就是為了讓這一步不再需要手動算像素座標。

操作方式：
    滑鼠左鍵   新增一個頂點
    滑鼠右鍵   完成目前的區域（至少三個頂點）
    N          完成目前區域，等同右鍵
    U          復原上一個頂點
    D          刪除最後一個已完成的區域
    C          清空全部
    S          存檔
    Q / Esc    離開（未存檔會先詢問）
    + / -      放大／縮小顯示（不影響實際座標）

使用範例：
    python tools/zone_editor.py
    python tools/zone_editor.py --video test_videos/my.mp4 --frame 300

建立日期：2026-10-03
版本號：v1.0.0
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

# 專案根目錄需在 sys.path 中才能匯入 utils
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.text_drawer import TextDrawer  # noqa: E402

_WINDOW = "Zone Editor"  # OpenCV 視窗標題不支援中文

# 各區域的顯示色（BGR），與主程式的 colors_of_roads 預設值一致
_COLORS = [
    (102, 204, 255),
    (80, 80, 240),
    (90, 200, 120),
    (200, 120, 220),
    (30, 165, 235),
    (200, 200, 80),
    (120, 120, 255),
    (80, 220, 220),
]

_FONT_CANDIDATES = [
    os.getenv("TRAFFIC_FONT_PATH", "C:/Windows/Fonts/msjh.ttc"),
    "C:/Windows/Fonts/msjhbd.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


class ZoneEditor:
    """道路區域多邊形編輯器。"""

    def __init__(self, frame: np.ndarray, existing: dict, output_path: str) -> None:
        """
        參數：
            frame:       要在上面繪製區域的影格（原始解析度）
            existing:    既有的區域座標，格式同 roads_polygons.json
            output_path: 存檔路徑
        """
        self.frame = frame
        self.output_path = output_path
        self.text_drawer = TextDrawer(_FONT_CANDIDATES, {"small": 16, "normal": 20})

        # 已完成的區域：[[(x, y), ...], ...]，索引 +1 即為道路編號
        self.polygons: list = []
        self.current: list = []   # 正在編輯中的頂點
        self.dirty = False        # 是否有未存檔的變更

        for key in sorted(existing, key=lambda k: int(k)):
            flat = existing[key]
            points = [(int(flat[i]), int(flat[i + 1])) for i in range(0, len(flat) - 1, 2)]
            if len(points) >= 3:
                self.polygons.append(points)

        # 視窗縮放：過大的影片要縮小才看得見全貌
        self.scale = self._initial_scale(frame.shape[1], frame.shape[0])

    @staticmethod
    def _initial_scale(width: int, height: int) -> float:
        """依影片尺寸決定初始縮放，盡量讓整張圖塞進常見螢幕。"""
        scale = min(1500.0 / width, 820.0 / height, 1.0)
        return round(max(scale, 0.2), 2)

    # ------------------------------------------------------------------
    # 滑鼠事件
    # ------------------------------------------------------------------
    def on_mouse(self, event, x, y, flags, param) -> None:
        """滑鼠回呼。顯示座標需換算回原始影像座標後才存入。"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.current.append((int(x / self.scale), int(y / self.scale)))
            self.dirty = True
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.finish_polygon()

    # ------------------------------------------------------------------
    # 編輯操作
    # ------------------------------------------------------------------
    def finish_polygon(self) -> str:
        """結束目前區域；頂點不足三個時不成立。"""
        if len(self.current) < 3:
            return "至少要三個頂點才能構成區域"
        self.polygons.append(self.current)
        self.current = []
        self.dirty = True
        return f"已完成道路 {len(self.polygons)}"

    def undo_point(self) -> str:
        if not self.current:
            return "沒有可復原的頂點"
        self.current.pop()
        self.dirty = True
        return "已復原一個頂點"

    def delete_last_polygon(self) -> str:
        if not self.polygons:
            return "沒有可刪除的區域"
        self.polygons.pop()
        self.dirty = True
        return f"已刪除最後一個區域，剩餘 {len(self.polygons)} 個"

    def clear_all(self) -> str:
        self.polygons = []
        self.current = []
        self.dirty = True
        return "已清空全部區域"

    def save(self) -> str:
        """輸出為 roads_polygons.json 的扁平座標格式。"""
        if not self.polygons:
            return "沒有任何區域可存檔"

        data = {}
        for index, points in enumerate(self.polygons, start=1):
            flat = []
            for x, y in points:
                flat.extend([int(x), int(y)])
            data[str(index)] = flat

        os.makedirs(os.path.dirname(os.path.abspath(self.output_path)), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

        self.dirty = False
        return f"已存檔：{self.output_path}（共 {len(self.polygons)} 個區域）"

    # ------------------------------------------------------------------
    # 繪製
    # ------------------------------------------------------------------
    def render(self, message: str) -> np.ndarray:
        """畫出目前狀態的畫面。"""
        canvas = self.frame.copy()
        text_items = []

        # 已完成的區域
        for index, points in enumerate(self.polygons):
            color = _COLORS[index % len(_COLORS)]
            array = np.array(points, dtype=np.int32)
            cv2.polylines(canvas, [array], isClosed=True, color=color, thickness=2)
            for point in points:
                cv2.circle(canvas, point, 4, color, -1)
            center = array.mean(axis=0).astype(int)
            text_items.append({
                "text": f"道路{index + 1}",
                "xy": (int(center[0]) - 28, int(center[1]) - 14),
                "color": (0, 0, 0), "size": "normal", "bg": color, "padding": 4,
            })

        # 編輯中的區域
        if self.current:
            array = np.array(self.current, dtype=np.int32)
            cv2.polylines(canvas, [array], isClosed=False, color=(255, 255, 255), thickness=2)
            for point in self.current:
                cv2.circle(canvas, point, 5, (255, 255, 255), -1)

        canvas = self.text_drawer.draw(canvas, text_items)
        canvas = self._attach_help(canvas, message)

        if self.scale != 1.0:
            canvas = cv2.resize(canvas, None, fx=self.scale, fy=self.scale,
                                interpolation=cv2.INTER_AREA)
        return canvas

    def _attach_help(self, canvas: np.ndarray, message: str) -> np.ndarray:
        """在畫面上方疊一條操作說明列。"""
        height, width = canvas.shape[:2]
        bar_height = 92
        bar = np.zeros((bar_height, width, 3), dtype=np.uint8)
        combined = np.vstack([bar, canvas])

        status = f"已完成 {len(self.polygons)} 個區域"
        if self.current:
            status += f"｜編輯中 {len(self.current)} 個頂點"
        if self.dirty:
            status += "｜尚未存檔"

        items = [
            {"text": "左鍵 新增頂點　右鍵/N 完成區域　U 復原頂點　D 刪除區域",
             "xy": (16, 10), "color": (235, 235, 235), "size": "small"},
            {"text": "C 清空　S 存檔　+/- 縮放　Q 離開",
             "xy": (16, 34), "color": (235, 235, 235), "size": "small"},
            {"text": status, "xy": (16, 60), "color": (150, 255, 180), "size": "small"},
        ]
        if message:
            items.append({"text": message, "xy": (width - 560, 60),
                          "color": (120, 220, 255), "size": "small"})

        return self.text_drawer.draw(combined, items)


def load_frame(video_path: str, frame_index: int) -> np.ndarray:
    """從影片取出指定影格。"""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"找不到影片檔案：{video_path}")

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"無法開啟影片：{video_path}")

    if frame_index > 0:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    capture.release()

    if not ok:
        raise RuntimeError(f"無法讀取第 {frame_index} 幀，請改用較小的 --frame 值")
    return frame


def load_existing(path: str) -> dict:
    """載入既有的區域設定；不存在時回傳空字典。"""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        print(f"[警告] 既有設定檔無法解析，將從空白開始：{path}")
        return {}


def parse_args():
    parser = argparse.ArgumentParser(
        description="道路區域座標編輯工具：在影片畫面上框選各條聯絡道的偵測區域。"
    )
    parser.add_argument(
        "--video",
        default=os.getenv("TRAFFIC_VIDEO_SRC", "test_videos/test_video.mp4"),
        help="要在上面框選區域的影片（預設讀取環境變數 TRAFFIC_VIDEO_SRC）",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("TRAFFIC_ROADS_INFO", "configs/roads_polygons.json"),
        help="區域座標的輸出路徑（預設讀取環境變數 TRAFFIC_ROADS_INFO）",
    )
    parser.add_argument(
        "--frame", type=int, default=0,
        help="取用第幾幀作為底圖，預設第 0 幀。車流較多的畫面較好判斷車道位置",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    frame = load_frame(args.video, args.frame)
    editor = ZoneEditor(frame, load_existing(args.output), args.output)

    print(f"影片：{args.video}（第 {args.frame} 幀，{frame.shape[1]}x{frame.shape[0]}）")
    print(f"輸出：{args.output}")
    print("操作說明顯示於視窗上方。按 S 存檔、Q 離開。")

    cv2.namedWindow(_WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(_WINDOW, editor.on_mouse)

    message = f"載入既有區域 {len(editor.polygons)} 個" if editor.polygons else ""

    while True:
        cv2.imshow(_WINDOW, editor.render(message))
        key = cv2.waitKey(20) & 0xFF

        if key == 255:
            continue
        if key in (ord("q"), ord("Q"), 27):
            if editor.dirty:
                message = "有未存檔的變更，請先按 S 存檔，或再按一次 Q 放棄"
                editor.dirty = False
                continue
            break
        elif key in (ord("n"), ord("N"), 13):
            message = editor.finish_polygon()
        elif key in (ord("u"), ord("U")):
            message = editor.undo_point()
        elif key in (ord("d"), ord("D")):
            message = editor.delete_last_polygon()
        elif key in (ord("c"), ord("C")):
            message = editor.clear_all()
        elif key in (ord("s"), ord("S")):
            message = editor.save()
            print(message)
        elif key in (ord("+"), ord("=")):
            editor.scale = round(min(editor.scale + 0.1, 2.0), 2)
            message = f"顯示縮放 {editor.scale}"
        elif key in (ord("-"), ord("_")):
            editor.scale = round(max(editor.scale - 0.1, 0.2), 2)
            message = f"顯示縮放 {editor.scale}"

    cv2.destroyAllWindows()
    print("已離開編輯器。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
