# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：車種對照與 PCU 當量
功能說明：
    將 YOLO（COCO 資料集）輸出的英文車種名稱轉換為繁體中文名稱，
    並提供小客車當量（PCU, Passenger Car Unit）換算。

    所有對照值皆由設定檔 configs/app_config.yaml 的 vehicle_types 區段注入，
    程式內不寫死任何數值，方便依不同分析情境調整當量。

備註：
    PCU 當量預設值參考台灣公路容量手冊之一般平面路口慣用值，
    實際應用應依標的路口特性於設定檔中調整。

建立日期：2025-01-24
版本號：v1.0.0
"""

from typing import Optional


class VehicleTypeRegistry:
    """車種名稱與 PCU 當量的對照表。"""

    def __init__(self, config: dict) -> None:
        """
        參數：
            config: 設定檔 vehicle_types 區段，需包含
                    name_mapping（英文→中文）與 pcu_factors（中文→當量）。
        """
        raw_mapping = config.get("name_mapping", {}) or {}
        raw_pcu = config.get("pcu_factors", {}) or {}

        # 統一轉小寫比對，避免模型輸出大小寫不一致造成對不到
        self._name_mapping = {str(k).lower(): str(v) for k, v in raw_mapping.items()}
        self._pcu_factors = {str(k): float(v) for k, v in raw_pcu.items()}

        # 未列於對照表的車種統一歸類，避免統計時出現空值
        self.unknown_label = str(config.get("unknown_label", "其他車種"))
        self.unknown_pcu = float(config.get("unknown_pcu", 1.0))

    @property
    def labels(self) -> list:
        """回傳所有已知的中文車種名稱，順序固定以便報表欄位穩定。"""
        ordered = list(dict.fromkeys(self._name_mapping.values()))
        ordered.append(self.unknown_label)
        return ordered

    def to_chinese(self, raw_name: Optional[str]) -> str:
        """把 YOLO 的英文類別名稱轉成中文車種名稱。"""
        if raw_name is None:
            return self.unknown_label
        return self._name_mapping.get(str(raw_name).lower(), self.unknown_label)

    def pcu_of(self, chinese_name: Optional[str]) -> float:
        """查詢中文車種對應的小客車當量（PCU）。"""
        if chinese_name is None:
            return self.unknown_pcu
        return self._pcu_factors.get(chinese_name, self.unknown_pcu)
