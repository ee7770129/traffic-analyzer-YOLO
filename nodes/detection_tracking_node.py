# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：車輛偵測與追蹤節點
功能說明：
    1. 以 YOLO 模型偵測畫面中的車輛。
    2. 以 ByteTrack 指派穩定的追蹤編號。
    3. 【本專案新增】把追蹤框比對回原始偵測框，還原被追蹤器抹除的車種資訊。

關於車種還原：
    原始專案在送入追蹤器前，會把所有物件的類別統一改成 car，
    以避免分類別追蹤造成的配對錯誤，代價是追蹤結果完全喪失車種資訊，
    因此無法做車種組成分析。

    本節點維持「統一類別送入追蹤器」的作法（不更動已驗證穩定的追蹤行為），
    改以 IoU 最大配對把每個追蹤框對回當幀的偵測框取得車種，
    再由 TrackElement 以生命週期多數決決定最終車種，兼顧穩定與正確。

建立日期：2025-01-06
版本號：v1.0.0
"""

import logging

import numpy as np
import torch
from ultralytics import YOLO

# 先註冊 vendor 路徑，byte_tracker 與 cython_bbox 相容層才找得到
import utils.vendor_path  # noqa: F401  （匯入即生效，不直接使用）
from byte_tracker.byte_tracker_model import BYTETracker

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from utils.geometry import iou_matrix
from utils.profiler import profile_time
from utils.vehicle_types import VehicleTypeRegistry

logger = logging.getLogger(__name__)

# 送入追蹤器的統一類別代碼（COCO 的 car），用於維持原專案的追蹤行為
_UNIFIED_TRACK_CLASS = 2


class DetectionTrackingNode:
    """YOLO 偵測 + ByteTrack 追蹤 + 車種還原。"""

    def __init__(self, config: dict) -> None:
        """
        參數：
            config: 完整設定檔，需包含 detection_node、tracking_node、vehicle_types 區段。
        """
        detection_cfg = config["detection_node"]
        tracking_cfg = config["tracking_node"]

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("車輛偵測將於 %s 上執行", str(self.device).upper())

        self.model = YOLO(detection_cfg["weight_pth"], task="detect")
        self.class_names = self.model.names

        self.confidence = float(detection_cfg["confidence"])
        self.iou = float(detection_cfg["iou"])
        self.imgsz = int(detection_cfg["imgsz"])
        self.classes_to_detect = [int(c) for c in detection_cfg["classes_to_detect"]]

        # 追蹤框對回偵測框所需的最低 IoU，低於此值視為配對失敗（車種留空）
        self.class_match_iou = float(detection_cfg.get("class_match_iou", 0.45))

        # ByteTrack 的 track_buffer 以幀為單位，故 fps 固定填 30 與原專案一致
        self.tracker = BYTETracker(
            30,
            float(tracking_cfg["first_track_thresh"]),
            float(tracking_cfg["second_track_thresh"]),
            float(tracking_cfg["match_thresh"]),
            int(tracking_cfg["track_buffer"]),
            1,
        )

        self.vehicle_types = VehicleTypeRegistry(config["vehicle_types"])

    @profile_time
    def process(self, element):
        """執行偵測與追蹤，並把結果寫回 FrameElement。"""
        if isinstance(element, StreamEndElement):
            return element

        assert isinstance(element, FrameElement), (
            f"DetectionTrackingNode｜輸入型別錯誤：{type(element)}"
        )

        outputs = self.model.predict(
            element.frame,
            imgsz=self.imgsz,
            conf=self.confidence,
            iou=self.iou,
            classes=self.classes_to_detect,
            verbose=False,
        )
        boxes = outputs[0].boxes

        # ---- 原始偵測結果（保留真實車種）----
        detected_xyxy = boxes.xyxy.cpu().numpy()
        detected_conf = boxes.conf.cpu().numpy()
        detected_cls_ids = boxes.cls.cpu().int().numpy()
        detected_labels = [
            self.vehicle_types.to_chinese(self.class_names[int(c)]) for c in detected_cls_ids
        ]

        element.detected_xyxy = detected_xyxy.astype(int).tolist()
        element.detected_conf = detected_conf.tolist()
        element.detected_cls = detected_labels

        # ---- 送入追蹤器（類別統一，維持原專案的追蹤行為）----
        track_inputs = self._build_tracker_input(detected_xyxy, detected_conf)
        tracks = self.tracker.update(torch.from_numpy(track_inputs), xyxy=True)

        element.tracked_ids = [int(t.track_id) for t in tracks]
        element.tracked_xyxy = [list(np.asarray(t.tlbr).astype(int)) for t in tracks]
        element.tracked_conf = [float(t.score) for t in tracks]

        # ---- 還原車種 ----
        element.tracked_cls = self._restore_vehicle_types(
            element.tracked_xyxy, detected_xyxy, detected_labels
        )

        return element

    def _build_tracker_input(self, detected_xyxy: np.ndarray, detected_conf: np.ndarray) -> np.ndarray:
        """
        組出 ByteTrack 需要的輸入陣列，每列為 [x1, y1, x2, y2, score, class]。
        無偵測結果時回傳空陣列，避免追蹤器取用形狀錯誤的張量。
        """
        if detected_xyxy.shape[0] == 0:
            return np.empty((0, 6), dtype=np.float32)

        class_column = np.full((detected_xyxy.shape[0], 1), _UNIFIED_TRACK_CLASS, dtype=np.float32)
        return np.hstack(
            [
                detected_xyxy.astype(np.float32),
                detected_conf.astype(np.float32).reshape(-1, 1),
                class_column,
            ]
        )

    def _restore_vehicle_types(
        self, tracked_xyxy: list, detected_xyxy: np.ndarray, detected_labels: list
    ) -> list:
        """
        以 IoU 最大配對，把每個追蹤框對應回當幀的偵測框以取得車種。

        追蹤器可能在物件被遮擋時以卡爾曼濾波預測位置，此時當幀沒有對應的偵測框，
        配對 IoU 會低於門檻，該幀回傳 None 不投票——這正是需要多數決的原因。

        回傳：
            與 tracked_xyxy 等長的串列，元素為中文車種名稱或 None。
        """
        if not tracked_xyxy or detected_xyxy.shape[0] == 0:
            return [None] * len(tracked_xyxy)

        overlaps = iou_matrix(tracked_xyxy, detected_xyxy)
        best_indices = overlaps.argmax(axis=1)
        best_scores = overlaps.max(axis=1)

        return [
            detected_labels[int(idx)] if score >= self.class_match_iou else None
            for idx, score in zip(best_indices, best_scores)
        ]
