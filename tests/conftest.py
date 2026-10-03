# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：測試共用設定（pytest conftest）
功能說明：
    1. 把專案根目錄加入 sys.path，讓測試能以 `from core...` 的方式匯入。
    2. 提供各測試共用的設定字典與物件工廠，避免每個測試檔重複建構。

建立日期：2026-10-03
版本號：v1.0.0
"""

import os
import sys

import pytest

# 專案根目錄必須在 sys.path 中，測試才能匯入 core / nodes / utils
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def vehicle_types_config() -> dict:
    """車種對照設定，與 configs/app_config.yaml 的 vehicle_types 區段同構。"""
    return {
        "name_mapping": {
            "car": "小客車",
            "motorcycle": "機車",
            "bus": "大客車",
            "truck": "大貨車",
        },
        "pcu_factors": {
            "小客車": 1.0,
            "機車": 0.5,
            "大客車": 2.0,
            "大貨車": 2.0,
        },
        "unknown_label": "其他車種",
        "unknown_pcu": 1.0,
    }


@pytest.fixture
def general_config() -> dict:
    """一般參數設定，門檻值刻意調小以便測試容易構造情境。"""
    return {
        "colors_of_roads": {1: [255, 0, 0], 2: [0, 255, 0], 3: [0, 0, 255]},
        "track_timeout_secs": 2.0,
        "min_track_life_secs": 1.0,
        "min_vote_count": 2,
        "flow_window_secs": 60.0,
    }


@pytest.fixture
def base_config(general_config, vehicle_types_config) -> dict:
    """組出節點建構所需的完整設定字典。"""
    return {
        "general": general_config,
        "vehicle_types": vehicle_types_config,
        "report_node": {
            "interval_seconds": 60.0,
            "csv_encoding": "utf-8-sig",
        },
    }


@pytest.fixture
def square_roads() -> dict:
    """
    三個互不重疊的方形區域，座標為扁平陣列，與 roads_polygons.json 同格式。

        區域1：(0,0)   ~ (100,100)
        區域2：(200,0) ~ (300,100)
        區域3：(0,200) ~ (100,300)
    """
    return {
        "1": [0, 0, 100, 0, 100, 100, 0, 100],
        "2": [200, 0, 300, 0, 300, 100, 200, 100],
        "3": [0, 200, 100, 200, 100, 300, 0, 300],
    }
