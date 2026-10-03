# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：utils/vehicle_types.py 的單元測試
功能說明：
    驗證車種中英對照與 PCU 當量查詢。PCU 直接影響容量分析的結果，
    未知車種的 fallback 行為尤其重要——不能讓未列入對照表的類別
    造成統計中斷或數值錯誤。

建立日期：2026-10-03
版本號：v1.0.0
"""

import pytest

from utils.vehicle_types import VehicleTypeRegistry


class TestToChinese:
    """英文類別名稱轉中文車種。"""

    def test_已知類別正確轉換(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.to_chinese("car") == "小客車"
        assert registry.to_chinese("motorcycle") == "機車"
        assert registry.to_chinese("bus") == "大客車"
        assert registry.to_chinese("truck") == "大貨車"

    def test_大小寫不敏感(self, vehicle_types_config):
        """模型輸出的大小寫不一致時仍要對得到。"""
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.to_chinese("CAR") == "小客車"
        assert registry.to_chinese("Motorcycle") == "機車"

    def test_未知類別歸入其他車種(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.to_chinese("bicycle") == "其他車種"

    def test_None_歸入其他車種(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.to_chinese(None) == "其他車種"


class TestPcuOf:
    """PCU 小客車當量查詢。"""

    def test_已知車種的當量(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.pcu_of("小客車") == pytest.approx(1.0)
        assert registry.pcu_of("機車") == pytest.approx(0.5)
        assert registry.pcu_of("大客車") == pytest.approx(2.0)

    def test_未知車種使用預設當量(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.pcu_of("飛機") == pytest.approx(1.0)

    def test_None_使用預設當量(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        assert registry.pcu_of(None) == pytest.approx(1.0)

    def test_當量可由設定檔調整(self):
        """當量必須完全來自設定，程式內不得寫死。"""
        registry = VehicleTypeRegistry(
            {
                "name_mapping": {"motorcycle": "機車"},
                "pcu_factors": {"機車": 0.3},
                "unknown_label": "其他",
                "unknown_pcu": 9.9,
            }
        )
        assert registry.pcu_of("機車") == pytest.approx(0.3)
        assert registry.pcu_of("未列入的") == pytest.approx(9.9)


class TestLabels:
    """報表欄位用的車種清單。"""

    def test_包含所有車種與未知類別(self, vehicle_types_config):
        registry = VehicleTypeRegistry(vehicle_types_config)
        labels = registry.labels
        assert labels == ["小客車", "機車", "大客車", "大貨車", "其他車種"]

    def test_順序固定以保證報表欄位穩定(self, vehicle_types_config):
        """不同影片跑出來的報表欄位結構必須一致，才能橫向比較。"""
        first = VehicleTypeRegistry(vehicle_types_config).labels
        second = VehicleTypeRegistry(vehicle_types_config).labels
        assert first == second

    def test_重複的中文名稱只出現一次(self):
        """多個英文類別對到同一個中文名稱時，欄位不應重複。"""
        registry = VehicleTypeRegistry(
            {
                "name_mapping": {"truck": "大貨車", "trailer": "大貨車"},
                "pcu_factors": {"大貨車": 2.0},
            }
        )
        assert registry.labels.count("大貨車") == 1


class TestDefaults:
    """設定缺漏時的預設行為。"""

    def test_空設定不會拋出例外(self):
        registry = VehicleTypeRegistry({})
        assert registry.to_chinese("car") == "其他車種"
        assert registry.pcu_of("car") == pytest.approx(1.0)
