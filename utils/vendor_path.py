# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：第三方套件路徑註冊
功能說明：
    專案將第三方 ByteTrack 追蹤器原樣保存在 vendor/byte_tracker/，
    其內部使用 `from byte_tracker.utils import ...` 這類絕對匯入，
    因此需要把 vendor/ 目錄加入 sys.path 才能正確載入。

    採用獨立模組而非在各處散落 sys.path 操作，
    使用端只要 `import utils.vendor_path` 即可，路徑邏輯集中於此。

建立日期：2024-12-18
版本號：v1.0.0
"""

import os
import sys

# 本檔案位於 <專案根目錄>/utils/，往上一層即為專案根目錄
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENDOR_DIR = os.path.join(_PROJECT_ROOT, "vendor")

# 專案根目錄需在路徑中，cython_bbox 相容層才找得到
for _path in (_PROJECT_ROOT, _VENDOR_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

PROJECT_ROOT = _PROJECT_ROOT
VENDOR_DIR = _VENDOR_DIR
