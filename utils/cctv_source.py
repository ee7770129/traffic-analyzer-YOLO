# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：路口 CCTV 影像來源解析
功能說明：
    把「路口預設組名稱」轉換成分析流水線可直接使用的影像來源：
        1. 從路口目錄檔（configs/cctv_cameras.yaml）查出該路口的攝影機編號、
           區域座標檔與計數線設定檔。
        2. 向交通局的攝影機頁面查詢目前的串流網址。

    為什麼不把串流網址直接寫進設定檔：
        交通局頁面內嵌的串流網址帶有一段代碼，無法保證長期不變。
        每次啟動時由攝影機編號即時查詢，網址更換後不必改設定。

資料來源：
    臺中市政府交通局 即時交通資訊（CCTV 開放資料）

建立日期：2026-10-08
版本號：v1.2.0
"""

import logging
import os
import re
import urllib.request
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# 攝影機頁面以 <img src="..."> 內嵌 MJPEG 串流
_STREAM_PATTERN = re.compile(r'<img[^>]*\ssrc="([^"]+)"', re.IGNORECASE)


class CctvSourceError(RuntimeError):
    """路口影像來源解析失敗（找不到預設組、頁面無法連線、頁面格式改變）。"""


def load_catalog(catalog_path: str) -> dict:
    """
    載入路口目錄檔。

    回傳：
        {"page_url_template": str, "request_timeout_secs": float, "cameras": {名稱: 設定}}
    """
    if not os.path.isfile(catalog_path):
        raise CctvSourceError(f"cctv_source｜找不到路口目錄檔：{catalog_path}")

    with open(catalog_path, "r", encoding="utf-8") as file:
        catalog = yaml.safe_load(file) or {}

    if not catalog.get("cameras"):
        raise CctvSourceError(f"cctv_source｜路口目錄檔沒有任何路口：{catalog_path}")
    return catalog


def extract_stream_url(page_html: str) -> Optional[str]:
    """由攝影機頁面的 HTML 取出串流網址；找不到時回傳 None。"""
    match = _STREAM_PATTERN.search(page_html or "")
    return match.group(1) if match else None


def fetch_stream_url(page_url: str, timeout_secs: float, opener=urllib.request.urlopen) -> str:
    """
    連線到攝影機頁面並取出串流網址。

    參數：
        opener: 實際發出連線的函式，測試時可替換以避免真的連網。
    """
    try:
        with opener(page_url, timeout=timeout_secs) as response:
            page_html = response.read().decode("utf-8", errors="ignore")
    except Exception as error:  # 網路層例外種類繁多，統一轉為本模組的錯誤
        raise CctvSourceError(f"cctv_source｜無法連線到攝影機頁面：{page_url}（{error}）") from error

    stream_url = extract_stream_url(page_html)
    if not stream_url:
        raise CctvSourceError(
            f"cctv_source｜攝影機頁面中找不到串流網址，頁面格式可能已變更：{page_url}"
        )
    return stream_url


def resolve_camera(camera_key: str, catalog: dict, opener=urllib.request.urlopen) -> dict:
    """
    把路口預設組名稱解析為影像來源設定。

    回傳：
        {"key", "name", "src", "roads_info", "lines_file"}
    """
    cameras = catalog["cameras"]
    if camera_key not in cameras:
        raise CctvSourceError(
            f"cctv_source｜找不到路口預設組「{camera_key}」，"
            f"可用的有：{', '.join(sorted(cameras))}"
        )

    camera = cameras[camera_key]
    page_url = str(catalog["page_url_template"]).format(camera_id=camera["camera_id"])
    timeout_secs = float(catalog.get("request_timeout_secs", 15))

    stream_url = fetch_stream_url(page_url, timeout_secs, opener)
    logger.info("路口「%s」串流網址：%s", camera.get("name", camera_key), stream_url)

    return {
        "key": camera_key,
        "name": camera.get("name", camera_key),
        "src": stream_url,
        "roads_info": camera["roads_info"],
        "lines_file": camera.get("lines_file"),
    }
