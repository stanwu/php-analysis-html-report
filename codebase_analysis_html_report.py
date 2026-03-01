#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_dumps_for_html(obj: Any) -> str:
    # Prevent accidental </script> termination when embedding JSON into HTML.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _norm_path(path: str) -> str:
    # Normalize to a forward-slash path for consistent directory splitting.
    return str(PurePosixPath(path.replace("\\", "/")))


def _dir_ancestors(file_path: str) -> list[str]:
    p = PurePosixPath(file_path)
    parts = list(p.parts)
    if len(parts) <= 1:
        return [""]
    dirs: list[str] = [""]
    for i in range(1, len(parts)):
        dirs.append("/".join(parts[:i]))
    return dirs


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


@dataclass(frozen=True)
class FileSummary:
    file_id: int
    path: str
    total_branches: int
    max_depth: int


def _compute_equal_width_hist(values: list[int], bins: int) -> dict[str, Any]:
    if not values:
        return {"min": 0, "max": 0, "bins": [{"lo": 0, "hi": 0, "count": 0, "label": "0"}]}

    vmin = min(values)
    vmax = max(values)
    if vmin == vmax:
        return {
            "min": vmin,
            "max": vmax,
            "bins": [{"lo": vmin, "hi": vmax, "count": len(values), "label": f"{vmin}"}],
        }

    bins = max(1, int(bins))
    width = (vmax - vmin) / bins
    # Guard for tiny ranges.
    if width <= 0:
        width = 1.0

    counts = [0] * bins
    for v in values:
        idx = int((v - vmin) / width)
        if idx == bins:
            idx = bins - 1
        if idx < 0:
            idx = 0
        counts[idx] += 1

    out_bins: list[dict[str, Any]] = []
    for i, c in enumerate(counts):
        lo = vmin + i * width
        hi = vmin + (i + 1) * width
        if i == bins - 1:
            hi = float(vmax)
        # Display labels as integers when possible.
        lo_i = int(math.floor(lo))
        hi_i = int(math.ceil(hi))
        label = f"{lo_i}–{hi_i}"
        out_bins.append({"lo": lo_i, "hi": hi_i, "count": c, "label": label})

    return {"min": vmin, "max": vmax, "bins": out_bins}


def _risk_score(total_branches_sum: int, max_depth_max: int, file_count: int) -> float:
    # Heuristic risk metric; tweakable without breaking the embedded schema.
    w1, w2, w3 = 1.5, 2.0, 0.1
    return w1 * math.log1p(total_branches_sum) + w2 * max_depth_max + w3 * file_count


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{TITLE}}</title>
    <style>
      :root{
        --bg:#f6f7fb;
        --panel:#ffffff;
        --panel2:#f8fafc;
        --text:#0f172a;
        --muted:#475569;
        --border:#e2e8f0;
        --accent:#2563eb;
        --danger:#e11d48;
        --good:#059669;
        --warn:#b45309;
        --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      }
      html,body{height:100%;}
      body{
        margin:0; font-family:var(--sans); color:var(--text); background:linear-gradient(180deg,#ffffff, var(--bg));
      }
      a{color:var(--accent); text-decoration:none;}
      a:hover{text-decoration:underline;}
      .app{min-height:100vh; display:grid; grid-template-columns: 360px 1fr;}
      @media (max-width: 980px){ .app{grid-template-columns: 1fr;} }
      .navpane{
        background:rgba(255,255,255,.92);
        border-right:1px solid var(--border);
        padding:12px;
        position:sticky;
        top:0;
        height:100vh;
        overflow:auto;
      }
      @media (max-width: 980px){
        .navpane{position:static; height:auto; border-right:none; border-bottom:1px solid var(--border);}
      }
      .navtitle{font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin:4px 2px 10px;}
      .wrap{max-width:1200px; margin:0; padding:24px;}
      header{display:flex; flex-direction:column; align-items:flex-start; justify-content:flex-start; gap:10px; margin-bottom:16px;}
      .title h1{margin:0; font-size:22px; letter-spacing:.2px;}
      .title .sub{margin-top:6px; color:var(--muted); font-size:13px; line-height:1.3;}
      .pill{display:inline-flex; gap:8px; align-items:center; padding:6px 10px; border:1px solid var(--border); background:rgba(255,255,255,.75); border-radius:999px; color:var(--muted); font-size:12px;}
      .grid{display:grid; grid-template-columns: 1fr; gap:12px;}
      .card{
        background:rgba(255,255,255,.85); border:1px solid var(--border); border-radius:14px;
        padding:14px; box-shadow: 0 12px 28px rgba(15,23,42,.08);
      }
      .card h2{margin:0 0 10px; font-size:14px; color:#0f172a; font-weight:650; letter-spacing:.2px;}
      .kpi{display:flex; gap:12px; align-items:baseline; flex-wrap:wrap;}
      .kpi .num{font-size:28px; font-weight:750; letter-spacing:.2px;}
      .kpi .lab{color:var(--muted); font-size:12px;}
      .banner{
        display:none; align-items:center; justify-content:space-between; gap:12px;
        border:1px solid rgba(225,29,72,.25); background:rgba(225,29,72,.06);
        padding:10px 12px; border-radius:12px; color:#9f1239; margin:12px 0 16px;
      }
      .banner strong{color:#881337;}
      .row{display:flex; gap:10px; flex-wrap:wrap; align-items:center;}
      .controls input[type="text"]{
        width:min(520px, 100%); padding:10px 12px; border-radius:12px;
        border:1px solid var(--border); background:rgba(248,250,252,.9); color:var(--text);
        outline:none;
      }
      .controls input[type="number"]{
        width:110px; padding:8px 10px; border-radius:12px;
        border:1px solid var(--border); background:rgba(248,250,252,.9); color:var(--text);
        outline:none;
      }
      .controls label{font-size:12px; color:var(--muted);}
      .btn{
        cursor:pointer; padding:8px 10px; border-radius:12px; border:1px solid var(--border);
        background:rgba(248,250,252,.9); color:var(--text);
      }
      .btn:hover{border-color:#35507a;}
      table{width:100%; border-collapse:collapse; font-size:12px;}
      th,td{padding:8px 8px; border-bottom:1px solid var(--border); vertical-align:top;}
      th{color:#0f172a; text-align:left; font-weight:650; position:sticky; top:0; background:rgba(255,255,255,.95); backdrop-filter: blur(6px);}
      td.mono{font-family:var(--mono); font-size:11.5px;}
      .muted{color:var(--muted);}
      .tree ul{list-style:none;margin:0;padding-left:18px}
      .tree details{margin:2px 0}
      .tree summary{cursor:pointer;color:var(--text)}
      .tree-file{margin:2px 0}
      .tree-file code{font-family:var(--mono); font-size:11.5px;}
      .tree-more{color:var(--muted); font-size:12px; margin:4px 0;}
      .split{display:grid; grid-template-columns: 1fr; gap:12px;}
      .tabs{display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 12px;}
      .tab{cursor:pointer; padding:8px 10px; border-radius:999px; border:1px solid var(--border); background:rgba(248,250,252,.95); color:var(--muted); font-size:12px;}
      .tab.active{color:var(--text); border-color:rgba(37,99,235,.35); background:rgba(37,99,235,.08);}
      .chart{height:320px;}
      .chart.small{height:260px;}
      pre{
        margin:0; padding:10px 12px; border-radius:12px; border:1px solid var(--border);
        background:rgba(248,250,252,.95); overflow:auto; color:#0f172a; font-size:12px;
      }
      .badge{
        display:inline-flex; align-items:center; gap:6px;
        padding:2px 8px; border-radius:999px; border:1px solid var(--border);
        background:rgba(248,250,252,.95); color:var(--muted); font-size:11px;
      }
      .badge.good{border-color:rgba(5,150,105,.25); color:#065f46;}
      .badge.warn{border-color:rgba(180,83,9,.25); color:#7c2d12;}
      .badge.danger{border-color:rgba(225,29,72,.25); color:#9f1239;}
      .click{cursor:pointer;}
      .click:hover{background:rgba(96,165,250,.08);}
      .two{display:grid; grid-template-columns: 1fr; gap:12px;}
      .right{display:flex; gap:8px; align-items:center; justify-content:flex-start; flex-wrap:wrap;}
      footer{margin-top:16px; color:var(--muted); font-size:12px;}
      .hidden{display:none;}
    </style>
  </head>
  <body>
    <div class="app">
      <aside class="navpane">
        <div class="navtitle">Explorer</div>
        <div class="card" style="box-shadow:none; background:rgba(248,250,252,.95);">
          <h2>Directory Drill-down</h2>
          <div class="row" style="justify-content:space-between; margin-bottom:8px;">
            <div class="muted">Current: <span id="dirCrumb" class="mono"></span></div>
            <div class="row">
              <button class="btn" id="dirUp">Up</button>
              <button class="btn" id="dirHome">Home</button>
            </div>
          </div>
          <div class="row" style="justify-content:flex-end; margin-bottom:8px;">
            <button class="btn" id="treeExpand">Expand</button>
            <button class="btn" id="treeCollapse">Collapse</button>
          </div>
          <div id="dirTree" class="tree" style="max-height: 320px; overflow:auto;"></div>
          <div id="dirTableWrap" style="max-height: 420px; overflow:auto; margin-top:12px;"></div>
        </div>
      </aside>

      <div class="main">
        <div class="wrap">
          <header>
            <div class="title">
              <h1>Codebase Complexity Report</h1>
              <div class="sub">
                Generated <span id="metaGeneratedAt" class="mono"></span> • Input <span id="metaInput" class="mono"></span>
                <span class="pill" style="margin-left:10px;"><span id="modeDot">●</span><span id="modeText">Loading…</span></span>
              </div>
            </div>
            <div class="right">
              <span class="pill">Files: <strong id="kFiles">–</strong></span>
              <span class="pill">Branches: <strong id="kBranches">–</strong></span>
              <span class="pill">Max depth: <strong id="kDepth">–</strong></span>
            </div>
          </header>

          <div class="card" style="margin-bottom:12px;">
            <h2>Overview</h2>
            <div class="kpi">
              <div>
                <div class="num" id="ovFiles">–</div>
                <div class="lab">Total files</div>
              </div>
              <div>
                <div class="num" id="ovBranches">–</div>
                <div class="lab">Total branches</div>
              </div>
            </div>
          </div>

          <div id="offlineBanner" class="banner">
            <div><strong>Offline fallback mode:</strong> interactive charts may be unavailable (CDN scripts failed to load).</div>
            <button class="btn" id="retryOnline">Retry online</button>
          </div>

          <div class="grid">
            <div class="card">
              <h2>Selection</h2>
              <div id="selectionMeta" class="muted">Select a directory or file…</div>
              <div style="margin-top:10px;">
                <div class="badge" id="selType"></div>
                <div class="badge" id="selBranches"></div>
                <div class="badge" id="selDepth"></div>
              </div>
              <div style="margin-top:10px;">
                <h2 style="margin-top:12px;">Details</h2>
                <div id="details"></div>
              </div>
            </div>

            <div class="card" style="grid-column: span 12;">
              <h2>Hotspots</h2>
              <div class="two">
                <div style="max-height: 420px; overflow:auto;">
                  <div class="muted" style="margin-bottom:8px;">Top by branches</div>
                  <div id="hotByBranches"></div>
                </div>
                <div style="max-height: 420px; overflow:auto;">
                  <div class="muted" style="margin-bottom:8px;">Top by depth</div>
                  <div id="hotByDepth"></div>
                </div>
              </div>
            </div>

            <div class="card" style="grid-column: span 12;">
              <h2>Files</h2>
              <div class="muted" id="fileListMeta" style="margin-bottom:8px;"></div>
              <div id="fileListWrap" style="max-height: 520px; overflow:auto;"></div>
              <div class="row" style="justify-content:flex-end; margin-top:10px;">
                <button class="btn" id="moreFiles">Show more</button>
              </div>
            </div>

            <div class="card" style="grid-column: span 12;">
              <h2>Charts (online)</h2>
              <div class="tabs">
                <div class="tab active" data-tab="branches">Branches</div>
                <div class="tab" data-tab="depth">Depth</div>
                <div class="tab" data-tab="hotspots">Hotspots</div>
              </div>
              <div id="chartBranches" class="chart"></div>
              <div id="chartDepth" class="chart hidden"></div>
              <div id="chartHotspots" class="chart hidden"></div>
              <div class="muted" style="margin-top:8px;">If charts are blank, the report is running in offline fallback mode.</div>
            </div>
          </div>

          <footer>
            Single-file HTML report. Works via <span class="mono">file://</span>. Online mode uses CDN for Plotly charts; offline fallback keeps tables and drill-down usable.
          </footer>
        </div>
      </div>
    </div>

    <script type="application/json" id="dataOverview">{{DATA_OVERVIEW}}</script>
    <script type="application/json" id="dataDirs">{{DATA_DIRS}}</script>
    <script type="application/json" id="dataFiles">{{DATA_FILES}}</script>
    <script type="application/json" id="dataDetails">{{DATA_DETAILS}}</script>

    <script>
      function $(id){ return document.getElementById(id); }
      function parseJsonScript(id){
        const el = $(id);
        if(!el) throw new Error("Missing data block: " + id);
        return JSON.parse(el.textContent);
      }
      function escapeHtml(s){
        return (""+s)
          .replaceAll("&","&amp;")
          .replaceAll("<","&lt;")
          .replaceAll(">","&gt;")
          .replaceAll('"',"&quot;")
          .replaceAll("'","&#039;");
      }
      function badge(kind, text){
        return '<span class="badge ' + kind + '">' + escapeHtml(text) + '</span>';
      }
      function scoreToKind(score){
        if(score >= 10) return "danger";
        if(score >= 6) return "warn";
        return "good";
      }
      function loadScript(src, timeoutMs){
        return new Promise((resolve, reject) => {
          const s = document.createElement("script");
          const t = setTimeout(() => reject(new Error("timeout")), timeoutMs || 4500);
          s.src = src;
          s.async = true;
          s.onload = () => { clearTimeout(t); resolve(); };
          s.onerror = () => { clearTimeout(t); reject(new Error("load failed")); };
          document.head.appendChild(s);
        });
      }

      const overview = parseJsonScript("dataOverview");
      const dirsData = parseJsonScript("dataDirs");
      const filesData = parseJsonScript("dataFiles");
      const detailsData = parseJsonScript("dataDetails");

      const files = filesData.files || [];
      const fileById = new Map(files.map(f => [f.id, f]));
      const fileIdByPath = new Map(files.map(f => [f.path, f.id]));

      const dirNodes = dirsData.nodes || {};
      const dirChildren = dirsData.children || {};
      const dirFiles = dirsData.files || {};
      const rootDir = (dirsData.root !== undefined) ? dirsData.root : "";

      let hasPlotly = false;
      let currentDir = rootDir;
      let fileListLimit = 200;
      let selected = {type:null, id:null};
      let wired = false;

      function isFilteredDir(dirId){
        // Hide the "valid" branch from the directory tree/drilldown views.
        if(!dirId) return false;
        const base = baseName(dirId);
        return base === "valid";
      }

      function isFilteredChildDir(dirId){
        // Filter the node itself or any descendant of a filtered node.
        if(!dirId) return false;
        if(isFilteredDir(dirId)) return true;
        return dirId.split("/").includes("valid");
      }

      function setMode(online){
        $("modeText").textContent = online ? "Online mode" : "Offline fallback";
        $("modeDot").style.color = online ? "#059669" : "#e11d48";
        $("offlineBanner").style.display = online ? "none" : "flex";
      }

      function initMeta(){
        $("metaGeneratedAt").textContent = overview.generated_at || "—";
        $("metaInput").textContent = overview.input || "—";
        $("ovFiles").textContent = overview.total_files ?? "—";
        $("ovBranches").textContent = overview.total_branches ?? "—";
        $("kFiles").textContent = overview.total_files ?? "—";
        $("kBranches").textContent = overview.total_branches ?? "—";
        $("kDepth").textContent = overview.max_depth_overall ?? "—";
      }

      function renderHotspots(){
        function renderTable(rows){
          let html = '<table><thead><tr><th>File</th><th>Branches</th><th>Depth</th></tr></thead><tbody>';
          for(const r of rows){
            html += '<tr class="click" data-file="' + escapeHtml(r.path) + '">';
            html += '<td class="mono">' + escapeHtml(r.path) + '</td>';
            html += '<td>' + escapeHtml(r.total_branches) + '</td>';
            html += '<td>' + escapeHtml(r.max_depth) + '</td>';
            html += '</tr>';
          }
          html += "</tbody></table>";
          return html;
        }
        $("hotByBranches").innerHTML = renderTable(overview.hotspots?.by_branches || []);
        $("hotByDepth").innerHTML = renderTable(overview.hotspots?.by_depth || []);

        for(const el of document.querySelectorAll("[data-file]")){
          el.addEventListener("click", () => selectFileByPath(el.getAttribute("data-file")));
        }
      }

      function fmtDirLabel(dir){
        return dir === "" ? "(root)" : dir;
      }

      function renderDirTable(dir){
        const children = (dirChildren[dir] || []).filter(d => !isFilteredChildDir(d));
        let html = '<table><thead><tr><th>Directory</th><th>Files</th><th>Branches sum</th><th>Max depth</th><th>Risk</th></tr></thead><tbody>';
        for(const child of children){
          const n = dirNodes[child];
          if(!n) continue;
          const kind = scoreToKind(n.score || 0);
          html += '<tr class="click" data-dir="' + escapeHtml(child) + '">';
          html += '<td class="mono">' + escapeHtml(fmtDirLabel(child)) + '</td>';
          html += '<td>' + escapeHtml(n.file_count ?? 0) + '</td>';
          html += '<td>' + escapeHtml(n.total_branches_sum ?? 0) + '</td>';
          html += '<td>' + escapeHtml(n.max_depth_max ?? 0) + '</td>';
          html += '<td>' + badge(kind, (n.score ?? 0).toFixed(2)) + '</td>';
          html += '</tr>';
        }
        html += "</tbody></table>";
        $("dirTableWrap").innerHTML = html;
        for(const el of document.querySelectorAll("[data-dir]")){
          el.addEventListener("click", () => selectDir(el.getAttribute("data-dir")));
        }
      }

      function baseName(path){
        const i = path.lastIndexOf("/");
        return i >= 0 ? path.slice(i+1) : path;
      }

      function ensureTreeChildren(detailsEl, dirId){
        const ul = detailsEl.querySelector("ul");
        if(!ul || ul.getAttribute("data-loaded") === "1") return;
        ul.setAttribute("data-loaded", "1");

        const childDirs = (dirChildren[dirId] || []).filter(d => !isFilteredChildDir(d)).slice();
        for(const d of childDirs){
          ul.appendChild(makeDirTreeNode(d));
        }

        const filesHere = (dirFiles[dirId] || []).slice();
        filesHere.sort((a,b) => {
          const fa = fileById.get(a); const fb = fileById.get(b);
          const pa = fa ? fa.path : ""; const pb = fb ? fb.path : "";
          return baseName(pa).localeCompare(baseName(pb)) || pa.localeCompare(pb);
        });

        const cap = 200;
        const shown = filesHere.slice(0, cap);
        for(const fid of shown){
          const f = fileById.get(fid);
          if(!f) continue;
          const li = document.createElement("li");
          li.className = "tree-file click";
          li.title = f.path;
          li.innerHTML = "<code>" + escapeHtml(baseName(f.path)) + "</code>";
          li.addEventListener("click", (e) => { e.stopPropagation(); selectFile(fid); });
          ul.appendChild(li);
        }
        if(filesHere.length > cap){
          const li = document.createElement("li");
          li.className = "tree-more";
          li.textContent = `… and ${filesHere.length - cap} more file(s) (see the Files section for full paths)`;
          ul.appendChild(li);
        }
      }

      function makeDirTreeNode(dirId){
        const li = document.createElement("li");
        li.className = "tree-dir";

        const det = document.createElement("details");
        det.setAttribute("data-dir", dirId);

        const sum = document.createElement("summary");
        const n = dirNodes[dirId] || {};
        const kind = scoreToKind(n.score || 0);
        sum.innerHTML =
          "<span class='mono'>" + escapeHtml(dirId === "" ? "(root)" : baseName(dirId)) + "</span> " +
          "<span class='muted'>(" + escapeHtml(n.file_count ?? 0) + " files)</span> " +
          badge(kind, (n.score ?? 0).toFixed(2));
        sum.addEventListener("click", (e) => {
          // Let <details> toggle, but also update selection.
          e.stopPropagation();
          selectDir(dirId);
        });
        det.appendChild(sum);

        const ul = document.createElement("ul");
        ul.setAttribute("data-loaded", "0");
        det.appendChild(ul);

        det.addEventListener("toggle", () => {
          if(det.open) ensureTreeChildren(det, dirId);
        });

        li.appendChild(det);
        return li;
      }

      function renderDirTree(dir){
        const root = $("dirTree");
        root.innerHTML = "";
        const container = document.createElement("ul");

        const childDirs = (dirChildren[dir] || []).filter(d => !isFilteredChildDir(d));
        const filesHere = dirFiles[dir] || [];
        if(childDirs.length === 0 && filesHere.length === 0){
          root.innerHTML = "<div class='muted'>No children under this directory.</div>";
          return;
        }

        // Render immediate children as open nodes (one level), lazily load deeper.
        for(const d of childDirs){
          const node = makeDirTreeNode(d);
          // Open immediate children and load their direct contents for a 1–2 level view.
          const det = node.querySelector("details");
          if(det){
            det.open = true;
            ensureTreeChildren(det, d);
          }
          container.appendChild(node);
        }

        // Also show files directly under current dir (not recursive).
        if(filesHere.length){
          const pseudo = document.createElement("li");
          pseudo.className = "tree-dir";
          const det = document.createElement("details");
          det.open = true;
          const sum = document.createElement("summary");
          sum.innerHTML = "<span class='muted'>Files in </span><span class='mono'>" + escapeHtml(fmtDirLabel(dir)) + "</span>";
          det.appendChild(sum);
          const ul = document.createElement("ul");
          ul.setAttribute("data-loaded", "1");
          det.appendChild(ul);
          const cap = 200;
          const shown = filesHere.slice().sort((a,b) => {
            const fa = fileById.get(a); const fb = fileById.get(b);
            const pa = fa ? fa.path : ""; const pb = fb ? fb.path : "";
            return baseName(pa).localeCompare(baseName(pb)) || pa.localeCompare(pb);
          }).slice(0, cap);
          for(const fid of shown){
            const f = fileById.get(fid);
            if(!f) continue;
            const li = document.createElement("li");
            li.className = "tree-file click";
            li.title = f.path;
            li.innerHTML = "<code>" + escapeHtml(baseName(f.path)) + "</code>";
            li.addEventListener("click", (e) => { e.stopPropagation(); selectFile(fid); });
            ul.appendChild(li);
          }
          if(filesHere.length > cap){
            const li = document.createElement("li");
            li.className = "tree-more";
            li.textContent = `… and ${filesHere.length - cap} more file(s) (see the Files section for full paths)`;
            ul.appendChild(li);
          }
          pseudo.appendChild(det);
          container.appendChild(pseudo);
        }

        root.appendChild(container);
      }

      function renderDirPanel(){
        selectDir(currentDir);
      }

      function selectDir(dir, opts){
        currentDir = dir;
        $("dirCrumb").textContent = fmtDirLabel(currentDir);
        renderDirTree(currentDir);
        renderDirTable(currentDir);
        if(opts && opts.silent) return;
        const n = dirNodes[dir] || {};
        selected = {type:"dir", id:dir};
        $("selectionMeta").innerHTML = "Directory: <span class='mono'>" + escapeHtml(fmtDirLabel(dir)) + "</span>";
        $("selType").textContent = "Directory";
        $("selBranches").textContent = "Branches sum: " + (n.total_branches_sum ?? 0);
        $("selDepth").textContent = "Max depth: " + (n.max_depth_max ?? 0);
        const top = (n.top_files || []).map(fid => fileById.get(fid)).filter(Boolean);
        let html = "";
        html += "<div class='muted'>Files: " + (n.file_count ?? 0) + " • Risk: " + (n.score ?? 0).toFixed(2) + "</div>";
        if(top.length){
          html += "<div style='margin-top:10px; max-height:260px; overflow:auto;'>";
          html += "<table><thead><tr><th>Top files</th><th>Branches</th><th>Depth</th></tr></thead><tbody>";
          for(const f of top){
            html += "<tr class='click' data-fileid='" + f.id + "'>";
            html += "<td class='mono'>" + escapeHtml(f.path) + "</td>";
            html += "<td>" + f.b + "</td>";
            html += "<td>" + f.d + "</td>";
            html += "</tr>";
          }
          html += "</tbody></table></div>";
        }else{
          html += "<div class='muted' style='margin-top:10px;'>No files under this directory.</div>";
        }
        $("details").innerHTML = html;
        for(const el of document.querySelectorAll("[data-fileid]")){
          el.addEventListener("click", () => selectFile(parseInt(el.getAttribute("data-fileid"),10)));
        }
      }

      function selectFile(fileId){
        const f = fileById.get(fileId);
        if(!f) return;
        selected = {type:"file", id:fileId};
        $("selectionMeta").innerHTML = "File: <span class='mono'>" + escapeHtml(f.path) + "</span>";
        $("selType").textContent = "File";
        $("selBranches").textContent = "Branches: " + f.b;
        $("selDepth").textContent = "Depth: " + f.d;

        const det = detailsData.details?.[fileId] || null;
        let html = "";
        html += "<div class='muted'>Summary: branches=" + f.b + ", max_depth=" + f.d + "</div>";
        if(!det){
          html += "<div class='muted' style='margin-top:10px;'>Full details not embedded for this file.</div>";
          $("details").innerHTML = html;
          return;
        }

        const funcs = det.functions || [];
        const branches = det.branches || [];
        html += "<div style='margin-top:10px;'>";
        html += "<div class='muted'>Embedded details: " + funcs.length + " function(s), " + branches.length + " branch(es)</div>";
        html += "<div style='margin-top:10px; max-height:260px; overflow:auto;'>";
        html += "<table><thead><tr><th>Branch</th><th>Line</th><th>Depth</th><th>Condition</th></tr></thead><tbody>";
        for(const b of branches){
          html += "<tr>";
          html += "<td>" + escapeHtml(b.type ?? "") + "</td>";
          html += "<td>" + escapeHtml(b.line ?? "") + "</td>";
          html += "<td>" + escapeHtml(b.depth ?? "") + "</td>";
          html += "<td class='mono'>" + escapeHtml(b.condition ?? "") + "</td>";
          html += "</tr>";
        }
        html += "</tbody></table></div>";
        html += "</div>";
        $("details").innerHTML = html;
      }

      function selectFileByPath(path){
        const fid = fileIdByPath.get(path);
        if(fid !== undefined) selectFile(fid);
      }

      function renderFileList(){
        $("fileListMeta").textContent = `Showing ${Math.min(fileListLimit, files.length)} of ${files.length} file(s)`;
        const shown = files
          .slice()
          .sort((a,b) => (b.b - a.b) || (b.d - a.d) || (a.path.localeCompare(b.path)))
          .slice(0, fileListLimit);

        let html = "<table><thead><tr><th>File</th><th>Branches</th><th>Depth</th></tr></thead><tbody>";
        for(const f of shown){
          html += "<tr class='click' data-fileid='" + f.id + "'>";
          html += "<td class='mono'>" + escapeHtml(f.path) + "</td>";
          html += "<td>" + f.b + "</td>";
          html += "<td>" + f.d + "</td>";
          html += "</tr>";
        }
        html += "</tbody></table>";
        $("fileListWrap").innerHTML = html;
        for(const el of document.querySelectorAll("#fileListWrap [data-fileid]")){
          el.addEventListener("click", () => selectFile(parseInt(el.getAttribute("data-fileid"),10)));
        }
        $("moreFiles").disabled = fileListLimit >= files.length;
      }

      function renderOfflineDistributions(){
        // In offline mode, we rely on tables already shown; charts remain blank.
        // Still ensure the active chart container isn't misleading.
        if(hasPlotly) return;
        $("chartBranches").innerHTML = "<div class='muted'>Offline fallback: charts unavailable.</div>";
        $("chartDepth").innerHTML = "<div class='muted'>Offline fallback: charts unavailable.</div>";
        $("chartHotspots").innerHTML = "<div class='muted'>Offline fallback: charts unavailable.</div>";
      }

      function renderChartsOnline(){
        if(!hasPlotly) return;
        const binsB = overview.distributions?.total_branches?.bins || [];
        const binsD = overview.distributions?.max_depth?.bins || [];
        const xB = binsB.map(b => b.label);
        const yB = binsB.map(b => b.count);
        const xD = binsD.map(b => b.label);
        const yD = binsD.map(b => b.count);

        const gridColor = "rgba(226,232,240,1)";
        const axisCommon = {
          tickangle: -30,
          gridcolor: gridColor,
          zerolinecolor: gridColor,
          linecolor: "rgba(203,213,225,1)",
          tickfont: {color: "#0f172a"},
        };

        Plotly.newPlot("chartBranches", [{
          type:"bar", x:xB, y:yB, marker:{color:"rgba(96,165,250,.75)"}
        }], {
          title:"Total branches distribution",
          margin:{l:40,r:10,t:40,b:80},
          paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
          font:{color:"#0f172a"},
          xaxis: axisCommon,
          yaxis: {gridcolor: gridColor, zerolinecolor: gridColor, linecolor: "rgba(203,213,225,1)", tickfont:{color:"#0f172a"}},
        }, {displayModeBar:false, responsive:true});

        Plotly.newPlot("chartDepth", [{
          type:"bar", x:xD, y:yD, marker:{color:"rgba(52,211,153,.75)"}
        }], {
          title:"Max depth distribution",
          margin:{l:40,r:10,t:40,b:80},
          paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
          font:{color:"#0f172a"},
          xaxis: axisCommon,
          yaxis: {gridcolor: gridColor, zerolinecolor: gridColor, linecolor: "rgba(203,213,225,1)", tickfont:{color:"#0f172a"}},
        }, {displayModeBar:false, responsive:true});

        const hot = overview.hotspots?.by_branches || [];
        Plotly.newPlot("chartHotspots", [{
          type:"bar",
          x: hot.map(r => r.total_branches).reverse(),
          y: hot.map(r => r.path).reverse(),
          orientation:"h",
          marker:{color:"rgba(251,191,36,.75)"}
        }], {
          title:"Top hotspots by branches",
          margin:{l:220,r:10,t:40,b:40},
          paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
          font:{color:"#0f172a"},
          xaxis: {gridcolor: gridColor, zerolinecolor: gridColor, linecolor: "rgba(203,213,225,1)", tickfont:{color:"#0f172a"}},
          yaxis: {gridcolor: gridColor, zerolinecolor: gridColor, linecolor: "rgba(203,213,225,1)", tickfont:{color:"#0f172a"}},
        }, {displayModeBar:false, responsive:true});
      }

      function wireTabs(){
        for(const t of document.querySelectorAll(".tab")){
          t.addEventListener("click", () => {
            for(const tt of document.querySelectorAll(".tab")) tt.classList.remove("active");
            t.classList.add("active");
            const which = t.getAttribute("data-tab");
            $("chartBranches").classList.toggle("hidden", which !== "branches");
            $("chartDepth").classList.toggle("hidden", which !== "depth");
            $("chartHotspots").classList.toggle("hidden", which !== "hotspots");
          });
        }
      }

      function wireControls(){
        $("moreFiles").addEventListener("click", () => {
          fileListLimit = Math.min(fileListLimit + 200, files.length);
          renderFileList();
        });

        $("dirHome").addEventListener("click", () => { currentDir = rootDir; renderDirPanel(); });
        $("dirUp").addEventListener("click", () => {
          if(currentDir === "") return;
          const parent = currentDir.includes("/") ? currentDir.split("/").slice(0,-1).join("/") : "";
          currentDir = parent;
          renderDirPanel();
        });
        $("treeExpand").addEventListener("click", () => {
          const root = $("dirTree");
          const nodes = root.querySelectorAll("details");
          nodes.forEach((d) => { d.open = true; });
          nodes.forEach((d) => {
            const dirId = d.getAttribute("data-dir");
            if(dirId) ensureTreeChildren(d, dirId);
          });
        });
        $("treeCollapse").addEventListener("click", () => {
          const root = $("dirTree");
          const nodes = root.querySelectorAll("details");
          nodes.forEach((d) => { d.open = false; });
        });
        $("retryOnline").addEventListener("click", () => init(true));
      }

      async function init(forceTryOnline){
        initMeta();
        if(!wired){
          wireTabs();
          wireControls();
          wired = true;
        }
        renderHotspots();
        renderFileList();

        if(forceTryOnline){
          try{
            await loadScript("https://cdn.plot.ly/plotly-2.30.0.min.js", 4500);
            hasPlotly = !!window.Plotly;
          }catch(e){
            hasPlotly = false;
          }
        }

        setMode(hasPlotly);
        renderOfflineDistributions();
        renderChartsOnline();
        renderDirPanel();
      }

      // First pass: attempt online; if it fails, fall back.
      init(true);
    </script>
  </body>
</html>
"""


def build_report(
    input_path: Path,
    output_path: Path,
    top_n: int,
    max_details: int,
    bins: int,
) -> None:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    summary = raw.get("summary") or {}
    files_raw = raw.get("files") or {}

    file_summaries: list[FileSummary] = []
    # Stable ordering for file IDs.
    for i, path in enumerate(sorted(files_raw.keys(), key=lambda p: _norm_path(str(p)))):
        item = files_raw.get(path) or {}
        file_summaries.append(
            FileSummary(
                file_id=i,
                path=_norm_path(str(path)),
                total_branches=_safe_int(item.get("total_branches"), 0),
                max_depth=_safe_int(item.get("max_depth"), 0),
            )
        )

    total_files = _safe_int((summary.get("total_files")), len(file_summaries))
    total_branches = _safe_int((summary.get("total_branches")), sum(f.total_branches for f in file_summaries))
    max_depth_overall = max([f.max_depth for f in file_summaries], default=0)

    top_n = max(1, int(top_n))
    max_details = max(0, int(max_details))
    bins = max(1, int(bins))

    hotspots_by_branches = sorted(
        file_summaries, key=lambda f: (-f.total_branches, -f.max_depth, f.path)
    )[:top_n]
    hotspots_by_depth = sorted(file_summaries, key=lambda f: (-f.max_depth, -f.total_branches, f.path))[
        :top_n
    ]

    dist_branches = _compute_equal_width_hist([f.total_branches for f in file_summaries], bins)
    dist_depth = _compute_equal_width_hist([f.max_depth for f in file_summaries], bins)

    # Directory aggregates over subtrees.
    # dir -> mutable agg
    dir_aggs: dict[str, dict[str, Any]] = {}

    def ensure_dir(dir_path: str) -> dict[str, Any]:
        if dir_path not in dir_aggs:
            dir_aggs[dir_path] = {
                "file_count": 0,
                "total_branches_sum": 0,
                "max_depth_max": 0,
                "top_files": [],  # will be filled later
            }
        return dir_aggs[dir_path]

    # Keep top files per directory via bounded list (small N) for simplicity.
    # Since max_details is likely small (<=200), top_n is small; still safe for 14k files.
    TOP_FILES_PER_DIR = max(5, min(50, top_n))

    top_files_work: dict[str, list[tuple[int, int, int, str]]] = {}  # dir -> [(b,d,id,path), ...]

    for f in file_summaries:
        for d in _dir_ancestors(f.path):
            a = ensure_dir(d)
            a["file_count"] += 1
            a["total_branches_sum"] += f.total_branches
            if f.max_depth > a["max_depth_max"]:
                a["max_depth_max"] = f.max_depth

            lst = top_files_work.setdefault(d, [])
            lst.append((f.total_branches, f.max_depth, f.file_id, f.path))

    # Finalize top files per directory, and scores.
    dir_nodes: dict[str, dict[str, Any]] = {}
    for d, a in dir_aggs.items():
        fc = int(a["file_count"])
        bs = int(a["total_branches_sum"])
        dm = int(a["max_depth_max"])
        score = float(_risk_score(bs, dm, fc))

        lst = top_files_work.get(d, [])
        lst.sort(key=lambda t: (-t[0], -t[1], t[3]))
        top_files = [t[2] for t in lst[:TOP_FILES_PER_DIR]]
        dir_nodes[d] = {
            "file_count": fc,
            "total_branches_sum": bs,
            "total_branches_avg": (bs / fc) if fc else 0.0,
            "max_depth_max": dm,
            "score": score,
            "top_files": top_files,
        }

    # Hierarchy adjacency (directories only).
    all_dirs = set(dir_nodes.keys())
    children: dict[str, list[str]] = {d: [] for d in all_dirs}
    for d in all_dirs:
        if d == "":
            continue
        parent = d.rsplit("/", 1)[0] if "/" in d else ""
        if parent not in children:
            children[parent] = []
        children[parent].append(d)
    for parent in list(children.keys()):
        children[parent] = sorted(children[parent])

    # Direct files per directory (for a lazy HTML <details> tree).
    dir_files: dict[str, list[int]] = {d: [] for d in all_dirs}
    for f in file_summaries:
        parent = f.path.rsplit("/", 1)[0] if "/" in f.path else ""
        dir_files.setdefault(parent, []).append(f.file_id)
    for d in list(dir_files.keys()):
        dir_files[d] = sorted(dir_files[d], key=lambda fid: file_summaries[fid].path)

    # File index for client-side search/filter.
    files_index = [{"id": f.file_id, "path": f.path, "b": f.total_branches, "d": f.max_depth} for f in file_summaries]

    # Embed full details for top max_details files (by branches then depth).
    selected_for_details = sorted(
        file_summaries, key=lambda f: (-f.total_branches, -f.max_depth, f.path)
    )[:max_details]
    selected_ids = {f.file_id for f in selected_for_details}
    details: dict[int, Any] = {}
    # Map from normalized path to raw key (since raw keys may differ slightly).
    raw_by_norm = {_norm_path(k): k for k in files_raw.keys()}
    for f in file_summaries:
        if f.file_id not in selected_ids:
            continue
        raw_key = raw_by_norm.get(f.path)
        if raw_key is None:
            continue
        item = files_raw.get(raw_key) or {}
        details[f.file_id] = {
            "branches": item.get("branches") or [],
            "functions": item.get("functions") or [],
        }

    def as_hotspot_row(f: FileSummary) -> dict[str, Any]:
        return {"path": f.path, "total_branches": f.total_branches, "max_depth": f.max_depth}

    overview_obj = {
        "generated_at": _utc_now_iso(),
        "input": str(input_path),
        "total_files": total_files,
        "total_branches": total_branches,
        "max_depth_overall": max_depth_overall,
        "hotspots": {
            "by_branches": [as_hotspot_row(f) for f in hotspots_by_branches],
            "by_depth": [as_hotspot_row(f) for f in hotspots_by_depth],
        },
        "distributions": {
            "total_branches": dist_branches,
            "max_depth": dist_depth,
        },
    }

    dirs_obj = {"root": "", "nodes": dir_nodes, "children": children, "files": dir_files}
    files_obj = {"files": files_index}
    details_obj = {"details": details}

    html = (
        HTML_TEMPLATE.replace("{{TITLE}}", "Codebase Complexity Report")
        .replace("{{DATA_OVERVIEW}}", _json_dumps_for_html(overview_obj))
        .replace("{{DATA_DIRS}}", _json_dumps_for_html(dirs_obj))
        .replace("{{DATA_FILES}}", _json_dumps_for_html(files_obj))
        .replace("{{DATA_DETAILS}}", _json_dumps_for_html(details_obj))
    )

    output_path.write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Convert analysis_report.json into a single-file HTML report (online charts via CDN, offline fallback)."
    )
    ap.add_argument("--input", default="analysis_report.json", help="Input JSON path (default: analysis_report.json)")
    ap.add_argument("--output", default="report.html", help="Output HTML path (default: report.html)")
    ap.add_argument("--top", type=int, default=20, help="Top N hotspots to show (default: 20)")
    ap.add_argument(
        "--max-details",
        type=int,
        default=50,
        help="Embed full details for up to M hottest files (default: 50)",
    )
    ap.add_argument("--bins", type=int, default=20, help="Histogram bins (default: 20)")
    args = ap.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    build_report(
        input_path=input_path,
        output_path=output_path,
        top_n=args.top,
        max_details=args.max_details,
        bins=args.bins,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
