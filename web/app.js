/*
  請務必保持 UTF-8 編碼。
  檔案名稱：成果展示網頁腳本
  功能說明：讀取 data/summary.json 並依其中的路口數量產生各路口的統計區塊。
            資料一律以 textContent 寫入，不組 HTML 字串，
            避免資料內容被當成標記執行。
  建立日期：2026-10-08
  最後更新：2026-10-09（改為可呈現多個路口）
  版本號：v1.2.0
*/

(function () {
  "use strict";

  var DATA_URL = "data/summary.json";
  var NUMERIC = /^-?\d+(\.\d+)?$/;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function icon(name) {
    return el("span", "material-symbols-outlined", name);
  }

  function formatDuration(seconds) {
    var total = Math.round(Number(seconds) || 0);
    var minutes = Math.floor(total / 60);
    var rest = total % 60;
    return minutes > 0 ? minutes + " 分 " + rest + " 秒" : rest + " 秒";
  }

  function addStat(container, label, value, unit) {
    var card = el("div", "stat");
    card.appendChild(el("div", "label", label));
    var valueNode = el("div", "value", String(value));
    if (unit) { valueNode.appendChild(el("span", "unit", unit)); }
    card.appendChild(valueNode);
    container.appendChild(card);
  }

  // 由越線計數表的「合計」列加總指定方向的車次
  function sumDirection(rows, direction) {
    return rows.slice(1).reduce(function (sum, row) {
      return row[2] === direction && row[3] === "合計" ? sum + Number(row[4]) : sum;
    }, 0);
  }

  function buildStats(item) {
    var container = el("div", "stats");
    var vehicles = item.vehicles || {};
    var lineRows = item.line_counts || [];

    addStat(container, "觀測長度", formatDuration(vehicles.duration_secs));
    addStat(container, "計入車輛", vehicles.total || 0, "輛");
    addStat(container, "越線進入路口", sumDirection(lineRows, "進入"), "車次");
    addStat(container, "越線離開路口", sumDirection(lineRows, "離開"), "車次");

    Object.keys(vehicles.by_type || {}).forEach(function (type) {
      addStat(container, type, vehicles.by_type[type], "輛");
    });
    return container;
  }

  // 把二維陣列畫成表格；純數字的儲存格靠右，含「合計」的列加強顯示
  function buildTable(rows, emptyText) {
    var wrapper = el("div", "table-scroll");
    var table = el("table");
    wrapper.appendChild(table);

    if (!rows || rows.length < 2) {
      table.insertRow().insertCell().textContent = emptyText;
      return wrapper;
    }

    var head = table.createTHead().insertRow();
    rows[0].forEach(function (text, index) {
      head.appendChild(el("th", index > 0 && NUMERIC.test(rows[1][index] || "") ? "num" : "", text));
    });

    var body = table.createTBody();
    rows.slice(1).forEach(function (cells) {
      var tr = body.insertRow();
      if (cells.indexOf("合計") !== -1) { tr.className = "total"; }
      cells.forEach(function (text) {
        var td = tr.insertCell();
        td.textContent = text;
        if (NUMERIC.test(text)) { td.className = "num"; }
      });
    });
    return wrapper;
  }

  function buildSubsection(iconName, title, hint, content) {
    var block = el("div", "subsection");
    var heading = el("h3");
    heading.appendChild(icon(iconName));
    heading.appendChild(document.createTextNode(title));
    block.appendChild(heading);
    if (hint) { block.appendChild(el("p", "hint", hint)); }
    block.appendChild(content);
    return block;
  }

  function buildIntersection(item) {
    var section = el("section", "panel intersection");
    var heading = el("h2");
    heading.appendChild(icon("traffic"));
    heading.appendChild(document.createTextNode(item.camera.name));
    section.appendChild(heading);
    section.appendChild(el("p", "hint",
      "攝影機解析度 " + item.camera.resolution + "　實測約 " + item.camera.measured_fps + " FPS"));

    section.appendChild(buildStats(item));

    section.appendChild(buildSubsection("swap_horiz", "越線計數",
      "每條聯絡道各設一條計數線，依車輛越線方向分為進入與離開。",
      buildTable(item.line_counts, "這次分析沒有越線紀錄。")));

    section.appendChild(buildSubsection("grid_on", "轉向矩陣",
      "列為進入的道路，欄為離開的道路。",
      buildTable(item.line_matrix, "這次分析沒有轉向紀錄。")));

    var heatmap = el("img", "shot");
    heatmap.src = item.heatmap;
    heatmap.alt = item.camera.name + " 的車輛位置熱力圖";
    heatmap.loading = "lazy";
    section.appendChild(buildSubsection("blur_on", "軌跡熱力圖",
      "顏色越暖代表車輛在該處累積停留的時間越長。車多的動線與停等位置都會變亮。", heatmap));

    section.appendChild(buildSubsection("schedule", "尖峰小時係數",
      "需連續觀測滿一小時才能計算；未滿時表格會註明原因。",
      buildTable(item.phf, "這次分析沒有尖峰小時係數資料。")));

    return section;
  }

  function renderCameras(data, analysedKeys) {
    var container = document.getElementById("cameras");
    (data.cameras || []).forEach(function (camera) {
      var isCurrent = analysedKeys.indexOf(camera.key) !== -1;
      var card = el("div", "camera" + (isCurrent ? " current" : ""));
      card.appendChild(el("div", "name", camera.name));
      card.appendChild(el("div", "spec",
        camera.resolution + "　約 " + camera.measured_fps + " FPS" + (isCurrent ? "　本頁分析對象" : "")));

      var link = el("a");
      link.href = camera.page_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.appendChild(icon("open_in_new"));
      link.appendChild(document.createTextNode("看即時影像"));
      card.appendChild(link);
      container.appendChild(card);
    });
  }

  function render(data) {
    var items = data.intersections || [];
    var names = items.map(function (item) { return item.camera.name; });

    document.getElementById("page-title").textContent = names.join("、") || "尚無分析資料";
    document.title = (names.join("、") || "台中路口") + "　車流分析";
    document.getElementById("run-meta").textContent =
      "資料產生時間 " + data.generated_at + "　共 " + items.length + " 個路口";

    var container = document.getElementById("intersections");
    items.forEach(function (item) { container.appendChild(buildIntersection(item)); });

    renderCameras(data, items.map(function (item) { return item.camera.key; }));
  }

  fetch(DATA_URL)
    .then(function (response) {
      if (!response.ok) { throw new Error("HTTP " + response.status); }
      return response.json();
    })
    .then(render)
    .catch(function (error) {
      document.getElementById("page-title").textContent = "無法載入分析資料";
      var notice = document.getElementById("load-error");
      notice.textContent = "讀不到 data/summary.json，請重新整理頁面；若仍失敗，代表資料尚未匯出。（" + error.message + "）";
      notice.hidden = false;
    });
})();
