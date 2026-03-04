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
        --bg:#f6f7fb; --panel:#ffffff; --panel2:#f8fafc;
        --text:#0f172a; --muted:#475569; --border:#e2e8f0;
        --accent:#2563eb; --danger:#e11d48; --good:#059669; --warn:#b45309;
        --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;
        --sans:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      }
      html,body{height:100%;}
      body{margin:0;font-family:var(--sans);color:var(--text);background:linear-gradient(180deg,#fff,var(--bg));}
      a{color:var(--accent);text-decoration:none;}

      /* ── Layout ── */
      .app{min-height:100vh;display:grid;grid-template-columns:300px 1fr;}
      @media(max-width:900px){.app{grid-template-columns:1fr;}}

      /* ── Sidebar ── */
      .navpane{
        background:rgba(255,255,255,.92);border-right:1px solid var(--border);
        position:sticky;top:0;height:100vh;overflow:auto;padding:10px 10px 20px;
      }
      @media(max-width:900px){.navpane{position:static;height:auto;border-right:none;border-bottom:1px solid var(--border);}}
      .navtitle{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:4px 2px 8px;}
      .filter-crumb{
        display:flex;align-items:center;gap:6px;flex-wrap:wrap;
        background:rgba(37,99,235,.07);border:1px solid rgba(37,99,235,.2);
        border-radius:8px;padding:5px 8px;font-size:12px;margin-bottom:8px;
      }
      .filter-crumb button{background:none;border:none;cursor:pointer;color:var(--muted);padding:0 2px;font-size:15px;line-height:1;}
      .tree ul{list-style:none;margin:0;padding-left:14px;}
      .tree details{margin:2px 0;}
      .tree summary{cursor:pointer;color:var(--text);font-size:12px;padding:2px 0;list-style:none;display:flex;align-items:center;gap:4px;}
      .tree summary::-webkit-details-marker{display:none;}
      .tree summary:hover{color:var(--accent);}
      .tree-leaf{display:flex;align-items:center;gap:4px;font-size:12px;padding:2px 0;cursor:pointer;}
      .tree-leaf:hover{color:var(--accent);}
      .dir-arrow{font-size:9px;color:var(--muted);transition:transform .15s;}
      details[open]>.dir-summary>.dir-arrow{transform:rotate(90deg);}

      /* ── Main ── */
      .main{overflow:auto;}
      .wrap{max-width:1280px;margin:0 auto;padding:14px 18px 24px;}

      /* ── Header ── */
      header{margin-bottom:12px;}
      .title-row{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:4px;}
      .title-row h1{margin:0;font-size:19px;letter-spacing:.2px;}
      .kpi-inline{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);flex-wrap:wrap;}
      .kpi-inline strong{color:var(--text);}
      .kpi-sep{color:var(--border);}
      .sub{color:var(--muted);font-size:12px;}

      /* ── Status bar ── */
      .status-bar{
        display:flex;gap:10px;flex-wrap:wrap;align-items:center;
        padding:8px 12px;border:1px solid var(--border);border-radius:10px;
        background:rgba(255,255,255,.85);margin-bottom:10px;font-size:12px;
      }
      .status-sep{width:1px;height:14px;background:var(--border);flex-shrink:0;}

      /* ── Banner ── */
      .banner{
        display:none;align-items:center;justify-content:space-between;gap:12px;
        border:1px solid rgba(225,29,72,.25);background:rgba(225,29,72,.06);
        padding:8px 12px;border-radius:10px;color:#9f1239;margin-bottom:10px;
      }
      .banner strong{color:#881337;}

      /* ── Controls bar ── */
      .controls-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px;}
      .controls-bar input[type="text"]{
        flex:1;min-width:180px;max-width:340px;padding:7px 10px;border-radius:8px;
        border:1px solid var(--border);background:rgba(248,250,252,.9);color:var(--text);
        outline:none;font-size:12.5px;font-family:inherit;
      }
      .controls-bar input[type="number"]{
        width:58px;padding:7px 8px;border-radius:8px;
        border:1px solid var(--border);background:rgba(248,250,252,.9);color:var(--text);
        outline:none;font-size:12.5px;
      }
      .controls-bar label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px;}
      .sev-btn{
        cursor:pointer;padding:5px 10px;border-radius:8px;border:1px solid var(--border);
        background:rgba(248,250,252,.9);color:var(--muted);font-size:12px;
      }
      .sev-btn.active{border-color:rgba(37,99,235,.4);background:rgba(37,99,235,.08);color:var(--text);}

      /* ── Section card ── */
      .section-card{
        background:rgba(255,255,255,.85);border:1px solid var(--border);border-radius:12px;
        padding:12px;margin-bottom:12px;box-shadow:0 4px 16px rgba(15,23,42,.06);
      }
      .section-card>h2{margin:0 0 10px;font-size:13px;font-weight:650;letter-spacing:.2px;}

      /* ── File table ── */
      .file-table{width:100%;border-collapse:collapse;font-size:12px;}
      .file-table th{
        padding:6px 8px;border-bottom:1px solid var(--border);text-align:left;
        font-weight:650;position:sticky;top:0;background:rgba(255,255,255,.97);
        backdrop-filter:blur(4px);white-space:nowrap;
      }
      .file-table td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle;}
      .file-row{cursor:pointer;transition:background .1s;}
      .file-row:hover{background:rgba(96,165,250,.07);}
      .file-row.expanded{background:rgba(37,99,235,.04);}
      .detail-row td{padding:0;background:var(--panel2);}
      .detail-content{padding:10px 12px 14px 36px;}
      .expand-icon{display:inline-block;font-size:9px;color:var(--muted);margin-right:4px;transition:transform .15s;width:10px;}
      .file-row.expanded .expand-icon{transform:rotate(90deg);}
      .start-badge{
        display:inline-block;background:var(--accent);color:#fff;
        border-radius:4px;padding:1px 5px;font-size:10px;font-weight:700;
        letter-spacing:.05em;margin-left:4px;vertical-align:middle;
      }

      /* ── Detail inner ── */
      .detail-inner{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
      @media(max-width:780px){.detail-inner{grid-template-columns:1fr;}}
      .section-label{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:6px;font-weight:600;}
      .func-table{width:100%;border-collapse:collapse;font-size:11.5px;}
      .func-table th,.func-table td{padding:5px 6px;border-bottom:1px solid var(--border);text-align:left;}
      .func-table th{font-weight:600;}
      .insight-box{
        margin-top:8px;padding:7px 10px;border-radius:8px;
        background:rgba(37,99,235,.06);border-left:3px solid var(--accent);
        font-size:11.5px;color:#1e40af;
      }
      .insight-box code{font-family:var(--mono);}

      /* ── Branch list ── */
      .branch-list{font-family:var(--mono);font-size:11.5px;}
      .branch-item{
        display:flex;align-items:baseline;gap:6px;padding:3px 0;
        border-bottom:1px solid rgba(226,232,240,.5);
      }
      .branch-item.bwarn{background:rgba(180,83,9,.04);}
      .branch-item.bdanger{background:rgba(225,29,72,.05);}
      .b-type{display:inline-block;min-width:54px;font-weight:600;color:var(--accent);font-size:11px;}
      .b-line{color:var(--muted);min-width:46px;}
      .b-cond{color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:260px;flex:1;}
      .depth-badge{display:inline-block;border-radius:3px;padding:0 4px;font-size:10px;font-weight:600;margin-left:auto;white-space:nowrap;}
      .depth-badge.ok{background:rgba(5,150,105,.1);color:#065f46;}
      .depth-badge.warn{background:rgba(180,83,9,.12);color:#7c2d12;}
      .depth-badge.danger{background:rgba(225,29,72,.12);color:#9f1239;}

      /* ── Impact footer ── */
      .impact-footer{font-size:12px;color:var(--muted);margin-top:8px;padding:6px 4px;border-top:1px solid var(--border);}
      .impact-footer strong{color:var(--text);}

      /* ── Charts ── */
      .tabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px;}
      .tab{cursor:pointer;padding:5px 10px;border-radius:999px;border:1px solid var(--border);background:rgba(248,250,252,.95);color:var(--muted);font-size:12px;}
      .tab.active{color:var(--text);border-color:rgba(37,99,235,.35);background:rgba(37,99,235,.08);}
      .chart{height:300px;}

      /* ── Common ── */
      .badge{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:999px;border:1px solid var(--border);font-size:11px;font-weight:500;}
      .badge.good{border-color:rgba(5,150,105,.25);color:#065f46;background:rgba(5,150,105,.06);}
      .badge.warn{border-color:rgba(180,83,9,.25);color:#7c2d12;background:rgba(180,83,9,.06);}
      .badge.danger{border-color:rgba(225,29,72,.25);color:#9f1239;background:rgba(225,29,72,.06);}
      .muted{color:var(--muted);}
      .mono{font-family:var(--mono);font-size:11.5px;}
      .btn{cursor:pointer;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:rgba(248,250,252,.9);color:var(--text);font-size:12px;}
      .btn:hover{border-color:#35507a;}
      .hidden{display:none;}
      .dup-badge{display:inline-block;background:rgba(147,51,234,.1);color:#7c3aed;border:1px solid rgba(147,51,234,.25);border-radius:4px;padding:0 5px;font-size:10px;font-weight:600;margin-left:4px;vertical-align:middle;}
      .dup-table{width:100%;border-collapse:collapse;font-size:12px;}
      .dup-table th{padding:6px 8px;border-bottom:1px solid var(--border);text-align:left;font-weight:650;position:sticky;top:0;background:rgba(255,255,255,.97);white-space:nowrap;}
      .dup-table td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle;}
      .dup-row{cursor:pointer;transition:background .1s;}
      .dup-row:hover{background:rgba(147,51,234,.05);}
      .dup-row.expanded{background:rgba(147,51,234,.04);}
      .dup-detail td{padding:0;background:var(--panel2);}
      .dup-paths{padding:8px 12px 10px 36px;font-family:var(--mono);font-size:11.5px;}
      .dup-paths div{padding:2px 0;border-bottom:1px solid rgba(226,232,240,.5);}
      .dup-paths div:last-child{border-bottom:none;}
      footer{margin-top:14px;color:var(--muted);font-size:11.5px;}
    </style>
  </head>
  <body>
    <div class="app">

      <!-- ── Sidebar: Directory filter ── -->
      <aside class="navpane">
        <div class="navtitle">Directory Filter</div>
        <div id="currentFilter" class="filter-crumb hidden">
          <span class="muted">In:</span>
          <span id="filterCrumbText" class="mono"></span>
          <button id="clearDirFilter" title="Show all files">✕</button>
        </div>
        <div id="dirTree" class="tree"></div>
      </aside>

      <!-- ── Main content ── -->
      <div class="main">
        <div class="wrap">

          <header>
            <div class="title-row">
              <h1>Codebase Complexity Report</h1>
              <div class="kpi-inline">
                <span>Files: <strong id="kFiles">–</strong></span>
                <span class="kpi-sep">|</span>
                <span>Branches: <strong id="kBranches">–</strong></span>
                <span class="kpi-sep">|</span>
                <span>Max depth: <strong id="kDepth">–</strong></span>
                <span class="kpi-sep">|</span>
                <span id="kDupWrap" class="hidden">Duplicates: <strong id="kDupGroups">–</strong> groups / <strong id="kDupFiles">–</strong> files</span>
                <span id="kDupSep" class="kpi-sep hidden">|</span>
                <span id="modePill" class="badge">Loading…</span>
              </div>
            </div>
            <div class="sub">
              Generated <span id="metaGeneratedAt" class="mono"></span>
              &nbsp;·&nbsp; Input <span id="metaInput" class="mono"></span>
            </div>
          </header>

          <div id="statusBar" class="status-bar"></div>

          <div id="offlineBanner" class="banner">
            <div><strong>Offline fallback:</strong> interactive charts unavailable (CDN failed to load).</div>
            <button class="btn" id="retryOnline">Retry online</button>
          </div>

          <!-- ── Controls ── -->
          <div class="controls-bar">
            <input type="text" id="searchInput" placeholder="Search file path… (Ctrl+F)" autocomplete="off" />
            <label>Branches ≥ <input type="number" id="filterBranches" min="0" value="0" /></label>
            <label>Depth ≥ <input type="number" id="filterDepth" min="0" value="0" /></label>
            <button class="sev-btn active" data-sev="all">All</button>
            <button class="sev-btn" data-sev="danger">🔴 Critical</button>
            <button class="sev-btn" data-sev="warn">🟡 Warning</button>
            <button class="sev-btn" data-sev="good">🟢 OK</button>
          </div>

          <!-- ── File list ── -->
          <div class="section-card">
            <h2>Files <span class="muted" id="fileCountLabel" style="font-weight:normal;font-size:12px;"></span></h2>
            <div id="fileTableWrap" style="max-height:580px;overflow:auto;"></div>
            <div id="impactFooter" class="impact-footer"></div>
            <div style="display:flex;justify-content:flex-end;margin-top:8px;">
              <button class="btn" id="moreFiles">Show more</button>
            </div>
          </div>

          <!-- ── Duplicates ── -->
          <div id="dupSection" class="section-card hidden">
            <h2>Duplicate Files <span class="muted" id="dupCountLabel" style="font-weight:normal;font-size:12px;"></span></h2>
            <div id="dupTableWrap" style="max-height:480px;overflow:auto;"></div>
            <div style="display:flex;justify-content:flex-end;margin-top:8px;">
              <button class="btn" id="moreDups">Show more</button>
            </div>
          </div>

          <!-- ── Charts ── -->
          <div class="section-card">
            <h2>Charts <span class="muted" style="font-weight:normal;font-size:12px;">(requires online mode)</span></h2>
            <div class="tabs">
              <div class="tab" data-tab="treemap">Directory map</div>
              <div class="tab" data-tab="branches">Branches dist.</div>
              <div class="tab" data-tab="depth">Depth dist.</div>
              <div class="tab active" data-tab="hotspots">Hotspots</div>
              <div class="tab" data-tab="duplicates" id="tabDuplicates" style="display:none;">Duplicates</div>
            </div>
            <div id="chartTreemap" class="chart hidden"></div>
            <div id="chartBranches" class="chart hidden"></div>
            <div id="chartDepth" class="chart hidden"></div>
            <div id="chartHotspots" class="chart"></div>
            <div id="chartDuplicates" class="chart hidden"></div>
            <div class="muted" style="font-size:12px;margin-top:6px;">Offline: charts unavailable — file table and filters remain fully functional.</div>
          </div>

          <footer>
            Single-file HTML report. Works via <span class="mono">file://</span>.
            Online mode uses CDN for Plotly charts; offline fallback keeps all tables and filters usable.
          </footer>
        </div>
      </div>
    </div>

    <script type="application/json" id="dataOverview">{{DATA_OVERVIEW}}</script>
    <script type="application/json" id="dataDirs">{{DATA_DIRS}}</script>
    <script type="application/json" id="dataFiles">{{DATA_FILES}}</script>
    <script type="application/json" id="dataDetails">{{DATA_DETAILS}}</script>
    <script type="application/json" id="dataDuplicates">{{DATA_DUPLICATES}}</script>

    <script>
      /* ── Utilities ── */
      function $(id){ return document.getElementById(id); }
      function parseJsonScript(id){
        const el=$(id); if(!el) throw new Error("Missing data block: "+id);
        return JSON.parse(el.textContent);
      }
      function escapeHtml(s){
        return (""+s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
          .replaceAll('"',"&quot;").replaceAll("'","&#039;");
      }
      function badge(kind,text){ return '<span class="badge '+kind+'">'+escapeHtml(text)+'</span>'; }
      function loadScript(src,ms){
        return new Promise((res,rej)=>{
          const s=document.createElement("script"),t=setTimeout(()=>rej(new Error("timeout")),ms||4500);
          s.src=src; s.async=true;
          s.onload=()=>{clearTimeout(t);res();};
          s.onerror=()=>{clearTimeout(t);rej(new Error("load failed"));};
          document.head.appendChild(s);
        });
      }
      function baseName(path){
        const i=path.lastIndexOf("/"); return i>=0?path.slice(i+1):path;
      }
      function parentDir(path){
        if(!path) return null;
        const i=path.lastIndexOf("/"); return i>=0?path.slice(0,i):"";
      }

      /* ── Data ── */
      const overview=parseJsonScript("dataOverview");
      const dirsData=parseJsonScript("dataDirs");
      const filesData=parseJsonScript("dataFiles");
      const detailsData=parseJsonScript("dataDetails");

      const files=filesData.files||[];
      const fileById=new Map(files.map(f=>[f.id,f]));
      const dirNodes=dirsData.nodes||{};
      const dirChildren=dirsData.children||{};
      const rootDir=(dirsData.root!==undefined)?dirsData.root:"";
      const dupData=parseJsonScript("dataDuplicates");
      const dupGroups=dupData.groups||[];
      const fileDupCount=dupData.file_dup_count||{};

      const TB=overview.threshold_branches||5;
      const TD=overview.threshold_depth||3;
      const totalBranches=overview.total_branches||1;

      /* ── State ── */
      let hasPlotly=false;
      let fileListLimit=200;
      let searchQuery="";
      let filterBranchesMin=0;
      let filterDepthMin=0;
      let filterSev="all";
      let filterDir=null;
      let wired=false;
      let dupListLimit=100;
      const expandedFiles=new Set();
      const expandedDups=new Set();

      /* ── Filtering helpers ── */
      function isFilteredChildDir(d){
        if(!d) return false;
        return d===("valid")||d.split("/").includes("valid");
      }
      function getSeverity(b,d){
        if(b>TB*2||d>TD*2) return "danger";
        if(b>TB||d>TD) return "warn";
        return "good";
      }
      function getDepthClass(depth){
        if(depth>=TD*1.5) return "danger";
        if(depth>=TD) return "warn";
        return "ok";
      }
      function getFilteredFiles(){
        return files.filter(f=>{
          if(searchQuery&&!f.path.toLowerCase().includes(searchQuery)) return false;
          if(filterBranchesMin>0&&f.b<filterBranchesMin) return false;
          if(filterDepthMin>0&&f.d<filterDepthMin) return false;
          if(filterDir!==null&&filterDir!==""){
            if(!f.path.startsWith(filterDir+"/")) return false;
          }
          if(filterSev!=="all"&&getSeverity(f.b,f.d)!==filterSev) return false;
          return true;
        }).sort((a,b)=>(b.b-a.b)||(b.d-a.d)||(a.path.localeCompare(b.path)));
      }

      /* ── Meta ── */
      function initMeta(){
        $("metaGeneratedAt").textContent=overview.generated_at||"—";
        $("metaInput").textContent=overview.input||"—";
        $("kFiles").textContent=overview.total_files??"—";
        $("kBranches").textContent=overview.total_branches??"—";
        $("kDepth").textContent=overview.max_depth_overall??"—";
        if((overview.duplicate_groups||0)>0){
          $("kDupGroups").textContent=overview.duplicate_groups;
          $("kDupFiles").textContent=overview.duplicate_files;
          $("kDupWrap").classList.remove("hidden");
          $("kDupSep").classList.remove("hidden");
        }
      }
      function setMode(online){
        $("modePill").textContent=online?"Online mode":"Offline fallback";
        $("modePill").className="badge "+(online?"good":"danger");
        $("offlineBanner").style.display=online?"none":"flex";
      }

      /* ── Status bar ── */
      function renderStatusBar(){
        const over=overview.over_threshold||{};
        const topMods=(overview.top_modules||[]).filter(m=>!isFilteredChildDir(m.dir));
        let html="";
        const ob=over.branches||0; const od=over.depth||0;
        if(ob>0) html+=`<span>${badge("danger","🔴 "+ob+" critical (branches > "+TB+")")}</span><span class="status-sep"></span>`;
        if(od>0) html+=`<span>${badge("warn","🟡 "+od+" deep (depth > "+TD+")")}</span><span class="status-sep"></span>`;
        if(ob===0&&od===0) html+=`<span>${badge("good","🟢 All files within threshold")}</span><span class="status-sep"></span>`;
        const dg=overview.duplicate_groups||0;
        if(dg>0) html+=`<span>${badge("warn","🟣 "+dg+" duplicate groups ("+overview.duplicate_waste+" redundant files)")}</span><span class="status-sep"></span>`;
        if(topMods.length){
          html+=`<span class="muted" style="font-size:11px;">Hotspot modules: `;
          html+=topMods.map(m=>`<strong class="mono">${escapeHtml(baseName(m.dir)||"(root)")}</strong> <span class="muted">${badge("danger",(m.score||0).toFixed(1))}</span>`).join(" &nbsp;");
          html+=`</span>`;
        }
        $("statusBar").innerHTML=html;
      }

      /* ── File table ── */
      function renderFileTable(){
        const filtered=getFilteredFiles();
        const shown=filtered.slice(0,fileListLimit);
        const dirLabel=filterDir===null?"":(" in "+(filterDir===""?"(root)":filterDir));
        $("fileCountLabel").textContent=`(${shown.length} of ${filtered.length}${dirLabel})`;
        $("moreFiles").disabled=fileListLimit>=filtered.length;
        $("moreFiles").textContent=fileListLimit>=filtered.length?"All shown":"Show more";

        let html='<table class="file-table"><thead><tr>';
        html+='<th style="width:96px;">Rank</th><th>File</th>';
        html+='<th style="width:74px;">Branches</th><th style="width:58px;">Depth</th>';
        html+='<th style="width:68px;">Impact</th><th style="width:82px;">Severity</th>';
        html+='</tr></thead><tbody>';

        for(let i=0;i<shown.length;i++){
          const f=shown[i]; const rank=i+1;
          const pct=totalBranches>0?(f.b/totalBranches*100):0;
          const sev=getSeverity(f.b,f.d);
          const sevLabel=sev==="danger"?"Critical":sev==="warn"?"Warning":"OK";
          const isExp=expandedFiles.has(f.id);
          html+=`<tr class="file-row${isExp?" expanded":""}" data-fid="${f.id}">`;
          html+=`<td><span class="expand-icon">▶</span>#${rank}${rank===1?'<span class="start-badge">START</span>':""}</td>`;
          const dupN=f.dup||0;
          html+=`<td class="mono">${escapeHtml(f.path)}${dupN>=2?'<span class="dup-badge">DUP ×'+dupN+'</span>':""}</td>`;
          html+=`<td>${f.b}</td><td>${f.d}</td>`;
          html+=`<td class="muted">${pct.toFixed(1)}%</td>`;
          html+=`<td>${badge(sev,sevLabel)}</td></tr>`;
          html+=`<tr class="detail-row${isExp?"":' hidden'}" id="dr-${f.id}">`;
          html+=`<td colspan="6"><div class="detail-content" id="dc-${f.id}">${isExp?renderFileDetailContent(f.id):""}</div></td></tr>`;
        }
        html+="</tbody></table>";
        $("fileTableWrap").innerHTML=html;

        for(const row of document.querySelectorAll(".file-row")){
          row.addEventListener("click",()=>toggleDetail(parseInt(row.dataset.fid)));
        }

        // Impact footer
        const topN=Math.min(3,shown.length);
        if(topN>0){
          let cum=0;
          for(let i=0;i<topN;i++) cum+=totalBranches>0?(shown[i].b/totalBranches*100):0;
          $("impactFooter").innerHTML=
            `Refactoring top <strong>${topN}</strong> file${topN>1?"s":""} eliminates `+
            `<strong>${cum.toFixed(0)}%</strong> of total branch complexity.`;
        } else {
          $("impactFooter").innerHTML="No files match the current filter.";
        }
      }

      /* ── Toggle detail row ── */
      function toggleDetail(fileId){
        const dr=$("dr-"+fileId); if(!dr) return;
        const isHidden=dr.classList.contains("hidden");
        const row=document.querySelector(".file-row[data-fid='"+fileId+"']");
        if(isHidden){
          expandedFiles.add(fileId);
          dr.classList.remove("hidden");
          if(row) row.classList.add("expanded");
          const dc=$("dc-"+fileId);
          if(dc&&!dc.dataset.rendered){ dc.innerHTML=renderFileDetailContent(fileId); dc.dataset.rendered="1"; }
        } else {
          expandedFiles.delete(fileId);
          dr.classList.add("hidden");
          if(row) row.classList.remove("expanded");
        }
      }

      /* ── File detail content ── */
      function renderFileDetailContent(fileId){
        const f=fileById.get(fileId); if(!f) return "";
        const det=detailsData.details?.[fileId]||null;
        if(!det) return `<div class="muted" style="font-size:12px;padding:4px 0;">Details not embedded for this file (outside top max-details). Summary: branches=${f.b}, max_depth=${f.d}</div>`;

        let html='<div class="detail-inner">';

        // Functions panel
        const funcs=(det.functions||[]).slice().sort((a,b)=>b.total_branches-a.total_branches);
        if(funcs.length){
          html+='<div><div class="section-label">Functions</div>';
          html+='<table class="func-table"><thead><tr><th>Function</th><th>Branches</th><th>Depth</th><th>% of file</th></tr></thead><tbody>';
          for(const fn of funcs){
            const pct=f.b>0?Math.round(fn.total_branches/f.b*100):0;
            const sev=getSeverity(fn.total_branches,fn.max_depth);
            html+=`<tr><td class="mono">${escapeHtml(fn.name)}()</td><td>${fn.total_branches}</td><td>${fn.max_depth}</td><td>${badge(sev,pct+"%")}</td></tr>`;
          }
          html+="</tbody></table>";
          if(funcs[0]&&f.b>0){
            const pct=Math.round(funcs[0].total_branches/f.b*100);
            if(pct>=50) html+=`<div class="insight-box">Refactoring <code>${escapeHtml(funcs[0].name)}()</code> eliminates <strong>${pct}%</strong> of this file's complexity.</div>`;
          }
          html+="</div>";
        }

        // Branches panel with depth indentation
        const branches=det.branches||[];
        if(branches.length){
          html+='<div><div class="section-label">Branch detail</div><div class="branch-list">';
          for(const b of branches){
            const indent=(b.depth||0)*14;
            const dc=getDepthClass(b.depth||0);
            html+=`<div class="branch-item ${dc==="ok"?"":"b"+dc}" style="padding-left:${indent+4}px">`;
            html+=`<span class="b-type">${escapeHtml(b.type||"")}</span>`;
            html+=`<span class="b-line">:${escapeHtml(String(b.line||""))}</span>`;
            if(b.condition) html+=`<span class="b-cond">${escapeHtml(b.condition)}</span>`;
            html+=`<span class="depth-badge ${dc}">d${b.depth||0}</span>`;
            html+="</div>";
          }
          html+="</div></div>";
        }

        html+="</div>";
        return html;
      }

      /* ── Duplicates table ── */
      function renderDuplicates(){
        if(!dupGroups.length){ $("dupSection").classList.add("hidden"); return; }
        $("dupSection").classList.remove("hidden");
        $("tabDuplicates").style.display="";
        const shown=dupGroups.slice(0,dupListLimit);
        $("dupCountLabel").textContent=`(${shown.length} of ${dupGroups.length} groups, ${overview.duplicate_files||0} files total)`;
        $("moreDups").disabled=dupListLimit>=dupGroups.length;
        $("moreDups").textContent=dupListLimit>=dupGroups.length?"All shown":"Show more";

        let html='<table class="dup-table"><thead><tr>';
        html+='<th style="width:50px;">#</th><th>Filename</th>';
        html+='<th style="width:70px;">Copies</th><th style="width:120px;">Checksum</th>';
        html+='</tr></thead><tbody>';

        for(let i=0;i<shown.length;i++){
          const g=shown[i]; const rank=i+1;
          const isExp=expandedDups.has(i);
          const name=baseName(g.paths[0]||"");
          html+=`<tr class="dup-row${isExp?" expanded":""}" data-di="${i}">`;
          html+=`<td><span class="expand-icon">▶</span>${rank}</td>`;
          html+=`<td class="mono">${escapeHtml(name)}</td>`;
          html+=`<td><span class="dup-badge">×${g.count}</span></td>`;
          html+=`<td class="mono muted" style="font-size:11px;">${escapeHtml(g.checksum)}…</td></tr>`;
          html+=`<tr class="dup-detail${isExp?"":" hidden"}" id="dd-${i}">`;
          html+=`<td colspan="4"><div class="dup-paths">`;
          if(isExp) for(const p of g.paths) html+=`<div>${escapeHtml(p)}</div>`;
          html+=`</div></td></tr>`;
        }
        html+="</tbody></table>";
        $("dupTableWrap").innerHTML=html;

        for(const row of document.querySelectorAll(".dup-row")){
          row.addEventListener("click",()=>toggleDupDetail(parseInt(row.dataset.di)));
        }
      }
      function toggleDupDetail(idx){
        const dr=$("dd-"+idx); if(!dr) return;
        const isHidden=dr.classList.contains("hidden");
        const row=document.querySelector(".dup-row[data-di='"+idx+"']");
        if(isHidden){
          expandedDups.add(idx);
          dr.classList.remove("hidden");
          if(row) row.classList.add("expanded");
          const paths=dr.querySelector(".dup-paths");
          if(paths&&!paths.dataset.rendered){
            const g=dupGroups[idx];
            paths.innerHTML=g.paths.map(p=>"<div>"+escapeHtml(p)+"</div>").join("");
            paths.dataset.rendered="1";
          }
        } else {
          expandedDups.delete(idx);
          dr.classList.add("hidden");
          if(row) row.classList.remove("expanded");
        }
      }

      /* ── Sidebar directory tree ── */
      function renderDirTree(){
        const root=$("dirTree"); root.innerHTML="";
        const ul=document.createElement("ul");

        // "All files" root entry
        const rootLi=document.createElement("li");
        const rootSpan=document.createElement("span");
        rootSpan.className="tree-leaf";
        const rn=dirNodes[rootDir]||{};
        rootSpan.innerHTML=`<span class="mono" style="color:var(--accent)">(all files)</span> <span class="muted">(${rn.file_count||0})</span>`;
        rootSpan.addEventListener("click",()=>setDirFilter(null));
        rootLi.appendChild(rootSpan); ul.appendChild(rootLi);

        function makeNode(dirId){
          const li=document.createElement("li");
          const children=(dirChildren[dirId]||[]).filter(d=>!isFilteredChildDir(d));
          const n=dirNodes[dirId]||{};
          const sev=getSeverity(n.total_branches_sum||0,n.max_depth_max||0);

          if(children.length){
            const det=document.createElement("details");
            const sum=document.createElement("summary");
            sum.className="dir-summary";
            sum.innerHTML=`<span class="dir-arrow">▶</span><span class="mono">${escapeHtml(baseName(dirId)||dirId)}</span> <span class="muted">(${n.file_count||0})</span> ${badge(sev,(n.score||0).toFixed(1))}`;
            sum.addEventListener("click",e=>{e.stopPropagation();setDirFilter(dirId);});
            det.appendChild(sum);
            const subUl=document.createElement("ul");
            det.addEventListener("toggle",()=>{
              if(det.open&&!subUl.dataset.loaded){
                subUl.dataset.loaded="1";
                for(const c of children) subUl.appendChild(makeNode(c));
              }
            });
            det.appendChild(subUl); li.appendChild(det);
          } else {
            const span=document.createElement("span");
            span.className="tree-leaf";
            span.innerHTML=`<span class="mono">${escapeHtml(baseName(dirId)||dirId)}</span> <span class="muted">(${n.file_count||0})</span> ${badge(sev,(n.score||0).toFixed(1))}`;
            span.addEventListener("click",()=>setDirFilter(dirId));
            li.appendChild(span);
          }
          return li;
        }

        const rootChildren=(dirChildren[rootDir]||[]).filter(d=>!isFilteredChildDir(d));
        for(const d of rootChildren) ul.appendChild(makeNode(d));
        root.appendChild(ul);
      }

      function setDirFilter(dirId){
        filterDir=dirId;
        fileListLimit=200;
        const crumb=$("currentFilter");
        if(dirId===null){ crumb.classList.add("hidden"); }
        else { $("filterCrumbText").textContent=dirId===""?"(root)":dirId; crumb.classList.remove("hidden"); }
        renderFileTable();
      }

      /* ── Charts ── */
      function renderChartsOnline(){
        if(!hasPlotly) return;
        const gridColor="rgba(226,232,240,1)";
        const axisCommon={tickangle:-30,gridcolor:gridColor,zerolinecolor:gridColor,linecolor:"rgba(203,213,225,1)",tickfont:{color:"#0f172a"}};
        const layout0={margin:{l:40,r:10,t:36,b:80},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#0f172a"}};

        // Treemap
        const allDirs=Object.keys(dirNodes).filter(d=>!isFilteredChildDir(d));
        const ids=allDirs.map(d=>d===""?"__root__":d);
        const labels=allDirs.map(d=>d===""?"(root)":baseName(d));
        const parents=allDirs.map(d=>{
          if(d==="") return "";
          const p=d.includes("/")?d.split("/").slice(0,-1).join("/"):"";
          return p===""?"__root__":p;
        });
        const values=allDirs.map(d=>(dirNodes[d]||{}).total_branches_sum||0);
        const colorMap={"danger":"rgba(225,29,72,.65)","warn":"rgba(251,191,36,.65)","good":"rgba(5,150,105,.55)"};
        const colors=allDirs.map(d=>{const n=dirNodes[d]||{};return colorMap[getSeverity(n.total_branches_sum||0,n.max_depth_max||0)];});
        Plotly.newPlot("chartTreemap",[{type:"treemap",ids,labels,parents,values,marker:{colors},textinfo:"label+value",hovertemplate:"<b>%{label}</b><br>Branches: %{value}<extra></extra>"}],
          {margin:{l:0,r:0,t:10,b:0},paper_bgcolor:"rgba(0,0,0,0)",font:{color:"#0f172a"}},{displayModeBar:false,responsive:true});

        // Histograms — top 5 bins by count
        const binsB=(overview.distributions?.total_branches?.bins||[]).slice().sort((a,b)=>b.count-a.count).slice(0,5);
        const binsD=(overview.distributions?.max_depth?.bins||[]).slice().sort((a,b)=>b.count-a.count).slice(0,5);
        Plotly.newPlot("chartBranches",[{type:"bar",x:binsB.map(b=>b.label),y:binsB.map(b=>b.count),marker:{color:"rgba(96,165,250,.75)"}}],
          {title:"Top 5 branch ranges",...layout0,xaxis:axisCommon,yaxis:{gridcolor:gridColor,zerolinecolor:gridColor,tickfont:{color:"#0f172a"}}},{displayModeBar:false,responsive:true});
        Plotly.newPlot("chartDepth",[{type:"bar",x:binsD.map(b=>b.label),y:binsD.map(b=>b.count),marker:{color:"rgba(52,211,153,.75)"}}],
          {title:"Top 5 depth ranges",...layout0,xaxis:axisCommon,yaxis:{gridcolor:gridColor,zerolinecolor:gridColor,tickfont:{color:"#0f172a"}}},{displayModeBar:false,responsive:true});

        // Hotspots bar — top 5 files
        const hot=(overview.hotspots?.by_branches||[]).slice(0,5);
        Plotly.newPlot("chartHotspots",[{type:"bar",x:hot.map(r=>r.total_branches).reverse(),y:hot.map(r=>r.path).reverse(),orientation:"h",marker:{color:"rgba(251,191,36,.75)"}}],
          {title:"Top hotspots by branches",margin:{l:220,r:10,t:36,b:40},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#0f172a"},
           xaxis:{gridcolor:gridColor,zerolinecolor:gridColor,tickfont:{color:"#0f172a"}},yaxis:{gridcolor:gridColor,tickfont:{color:"#0f172a"}}},{displayModeBar:false,responsive:true});

        // Duplicates bar — top 10 groups by copy count
        if(dupGroups.length){
          const topDup=dupGroups.slice(0,10);
          Plotly.newPlot("chartDuplicates",[{type:"bar",x:topDup.map(g=>g.count).reverse(),y:topDup.map(g=>baseName(g.paths[0]||"")).reverse(),orientation:"h",marker:{color:"rgba(147,51,234,.65)"}}],
            {title:"Top duplicate file groups by copy count",margin:{l:220,r:10,t:36,b:40},paper_bgcolor:"rgba(0,0,0,0)",plot_bgcolor:"rgba(0,0,0,0)",font:{color:"#0f172a"},
             xaxis:{gridcolor:gridColor,zerolinecolor:gridColor,tickfont:{color:"#0f172a"},dtick:1},yaxis:{gridcolor:gridColor,tickfont:{color:"#0f172a"}}},{displayModeBar:false,responsive:true});
        }
      }

      function renderOfflineDistributions(){
        if(hasPlotly) return;
        for(const id of["chartTreemap","chartBranches","chartDepth","chartHotspots","chartDuplicates"])
          $(id).innerHTML="<div class='muted' style='padding:16px;'>Offline fallback: chart unavailable.</div>";
      }

      /* ── Wire tabs ── */
      function wireTabs(){
        const tabMap={treemap:"chartTreemap",branches:"chartBranches",depth:"chartDepth",hotspots:"chartHotspots",duplicates:"chartDuplicates"};
        const chartIds=Object.values(tabMap);
        for(const t of document.querySelectorAll(".tab")){
          t.addEventListener("click",()=>{
            for(const tt of document.querySelectorAll(".tab")) tt.classList.remove("active");
            t.classList.add("active");
            const target=tabMap[t.dataset.tab];
            for(const id of chartIds) $(id).classList.toggle("hidden",id!==target);
          });
        }
      }

      /* ── Wire controls ── */
      function wireControls(){
        $("searchInput").addEventListener("input",e=>{searchQuery=e.target.value.toLowerCase();fileListLimit=200;renderFileTable();});
        $("filterBranches").addEventListener("input",e=>{filterBranchesMin=parseInt(e.target.value)||0;fileListLimit=200;renderFileTable();});
        $("filterDepth").addEventListener("input",e=>{filterDepthMin=parseInt(e.target.value)||0;fileListLimit=200;renderFileTable();});
        for(const btn of document.querySelectorAll(".sev-btn")){
          btn.addEventListener("click",()=>{
            for(const b of document.querySelectorAll(".sev-btn")) b.classList.remove("active");
            btn.classList.add("active"); filterSev=btn.dataset.sev; fileListLimit=200; renderFileTable();
          });
        }
        $("moreFiles").addEventListener("click",()=>{fileListLimit+=200;renderFileTable();});
        $("moreDups").addEventListener("click",()=>{dupListLimit+=100;renderDuplicates();});
        $("clearDirFilter").addEventListener("click",()=>setDirFilter(null));
        $("retryOnline").addEventListener("click",()=>init(true));
        document.addEventListener("keydown",e=>{
          if((e.ctrlKey||e.metaKey)&&e.key==="f"&&document.activeElement!==$("searchInput")){
            e.preventDefault(); $("searchInput").focus(); $("searchInput").select();
          }
        });
      }

      /* ── Init ── */
      async function init(forceTryOnline){
        initMeta();
        if(!wired){ wireTabs(); wireControls(); wired=true; }
        renderStatusBar();
        renderDirTree();
        renderFileTable();
        renderDuplicates();

        if(forceTryOnline){
          try{
            await loadScript("https://cdn.plot.ly/plotly-2.30.0.min.js",4500);
            hasPlotly=!!window.Plotly;
          }catch(e){ hasPlotly=false; }
        }
        setMode(hasPlotly);
        renderOfflineDistributions();
        renderChartsOnline();
      }

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
    threshold_branches: int = 5,
    threshold_depth: int = 3,
) -> None:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    summary = raw.get("summary") or {}
    files_raw = raw.get("files") or {}
    duplicates_raw: dict[str, list[str]] = summary.get("duplicates") or {}

    file_summaries: list[FileSummary] = []
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

    # Build duplicate groups cross-referenced with file_ids.
    path_to_id = {f.path: f.file_id for f in file_summaries}
    dup_groups: list[dict[str, Any]] = []
    file_id_dup_count: dict[int, int] = {}
    for checksum, paths in duplicates_raw.items():
        norm_paths = [_norm_path(p) for p in paths]
        fids = [path_to_id[p] for p in norm_paths if p in path_to_id]
        if len(fids) >= 2:
            dup_groups.append({"checksum": checksum[:12], "count": len(fids), "file_ids": fids, "paths": norm_paths})
            for fid in fids:
                file_id_dup_count[fid] = len(fids)
    dup_groups.sort(key=lambda g: (-g["count"], g["checksum"]))
    dup_total_files = sum(g["count"] for g in dup_groups)
    dup_waste = dup_total_files - len(dup_groups)

    total_files = _safe_int(summary.get("total_files"), len(file_summaries))
    total_branches = _safe_int(summary.get("total_branches"), sum(f.total_branches for f in file_summaries))
    max_depth_overall = max([f.max_depth for f in file_summaries], default=0)

    top_n = max(1, int(top_n))
    max_details = max(0, int(max_details))
    bins = max(1, int(bins))
    threshold_branches = max(1, int(threshold_branches))
    threshold_depth = max(1, int(threshold_depth))

    hotspots_by_branches = sorted(
        file_summaries, key=lambda f: (-f.total_branches, -f.max_depth, f.path)
    )[:top_n]
    hotspots_by_depth = sorted(
        file_summaries, key=lambda f: (-f.max_depth, -f.total_branches, f.path)
    )[:top_n]

    dist_branches = _compute_equal_width_hist([f.total_branches for f in file_summaries], bins)
    dist_depth = _compute_equal_width_hist([f.max_depth for f in file_summaries], bins)

    # Directory aggregates.
    dir_aggs: dict[str, dict[str, Any]] = {}

    def ensure_dir(dir_path: str) -> dict[str, Any]:
        if dir_path not in dir_aggs:
            dir_aggs[dir_path] = {"file_count": 0, "total_branches_sum": 0, "max_depth_max": 0, "top_files": []}
        return dir_aggs[dir_path]

    TOP_FILES_PER_DIR = max(5, min(50, top_n))
    top_files_work: dict[str, list[tuple[int, int, int, str]]] = {}

    for f in file_summaries:
        for d in _dir_ancestors(f.path):
            a = ensure_dir(d)
            a["file_count"] += 1
            a["total_branches_sum"] += f.total_branches
            if f.max_depth > a["max_depth_max"]:
                a["max_depth_max"] = f.max_depth
            top_files_work.setdefault(d, []).append((f.total_branches, f.max_depth, f.file_id, f.path))

    dir_nodes: dict[str, dict[str, Any]] = {}
    for d, a in dir_aggs.items():
        fc = int(a["file_count"])
        bs = int(a["total_branches_sum"])
        dm = int(a["max_depth_max"])
        score = float(_risk_score(bs, dm, fc))
        lst = top_files_work.get(d, [])
        lst.sort(key=lambda t: (-t[0], -t[1], t[3]))
        dir_nodes[d] = {
            "file_count": fc,
            "total_branches_sum": bs,
            "total_branches_avg": (bs / fc) if fc else 0.0,
            "max_depth_max": dm,
            "score": score,
            "top_files": [t[2] for t in lst[:TOP_FILES_PER_DIR]],
        }

    # Hierarchy.
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

    dir_files: dict[str, list[int]] = {d: [] for d in all_dirs}
    for f in file_summaries:
        parent = f.path.rsplit("/", 1)[0] if "/" in f.path else ""
        dir_files.setdefault(parent, []).append(f.file_id)
    for d in list(dir_files.keys()):
        dir_files[d] = sorted(dir_files[d], key=lambda fid: file_summaries[fid].path)

    files_index = [
        {
            "id": f.file_id, "path": f.path, "b": f.total_branches, "d": f.max_depth,
            **({"dup": file_id_dup_count[f.file_id]} if f.file_id in file_id_dup_count else {}),
        }
        for f in file_summaries
    ]

    # Details for top files.
    selected_ids = {f.file_id for f in sorted(file_summaries, key=lambda f: (-f.total_branches, -f.max_depth, f.path))[:max_details]}
    details: dict[int, Any] = {}
    raw_by_norm = {_norm_path(k): k for k in files_raw.keys()}
    for f in file_summaries:
        if f.file_id not in selected_ids:
            continue
        raw_key = raw_by_norm.get(f.path)
        if raw_key is None:
            continue
        item = files_raw.get(raw_key) or {}
        details[f.file_id] = {"branches": item.get("branches") or [], "functions": item.get("functions") or []}

    # Over-threshold counts.
    over_branches = sum(1 for f in file_summaries if f.total_branches > threshold_branches)
    over_depth = sum(1 for f in file_summaries if f.max_depth > threshold_depth)

    # Top hotspot modules (non-root, non-filtered dirs).
    top_modules = sorted(
        [{"dir": d, "score": n["score"], "file_count": n["file_count"]}
         for d, n in dir_nodes.items() if d],
        key=lambda x: -x["score"],
    )[:3]

    # Hotspot rows with rank and impact %.
    tb_nz = max(total_branches, 1)

    def as_hotspot_row(rank: int, f: FileSummary) -> dict[str, Any]:
        return {
            "rank": rank,
            "path": f.path,
            "total_branches": f.total_branches,
            "max_depth": f.max_depth,
            "pct_branches": round(f.total_branches / tb_nz * 100, 1),
        }

    overview_obj = {
        "generated_at": _utc_now_iso(),
        "input": str(input_path),
        "total_files": total_files,
        "total_branches": total_branches,
        "max_depth_overall": max_depth_overall,
        "threshold_branches": threshold_branches,
        "threshold_depth": threshold_depth,
        "over_threshold": {"branches": over_branches, "depth": over_depth},
        "top_modules": top_modules,
        "hotspots": {
            "by_branches": [as_hotspot_row(i + 1, f) for i, f in enumerate(hotspots_by_branches)],
            "by_depth": [as_hotspot_row(i + 1, f) for i, f in enumerate(hotspots_by_depth)],
        },
        "distributions": {"total_branches": dist_branches, "max_depth": dist_depth},
        "duplicate_groups": len(dup_groups),
        "duplicate_files": dup_total_files,
        "duplicate_waste": dup_waste,
    }

    dirs_obj = {"root": "", "nodes": dir_nodes, "children": children, "files": dir_files}
    files_obj = {"files": files_index}
    details_obj = {"details": details}
    duplicates_obj = {"groups": dup_groups, "file_dup_count": file_id_dup_count}

    html = (
        HTML_TEMPLATE.replace("{{TITLE}}", "Codebase Complexity Report")
        .replace("{{DATA_OVERVIEW}}", _json_dumps_for_html(overview_obj))
        .replace("{{DATA_DIRS}}", _json_dumps_for_html(dirs_obj))
        .replace("{{DATA_FILES}}", _json_dumps_for_html(files_obj))
        .replace("{{DATA_DETAILS}}", _json_dumps_for_html(details_obj))
        .replace("{{DATA_DUPLICATES}}", _json_dumps_for_html(duplicates_obj))
    )

    output_path.write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Convert analysis_report.json into a single-file HTML report (online charts via CDN, offline fallback)."
    )
    ap.add_argument("--input", default="analysis_report.json", help="Input JSON path (default: analysis_report.json)")
    ap.add_argument("--output", default="report.html", help="Output HTML path (default: report.html)")
    ap.add_argument("--top", type=int, default=20, help="Top N hotspots to show (default: 20)")
    ap.add_argument("--max-details", type=int, default=50, help="Embed full details for up to M hottest files (default: 50)")
    ap.add_argument("--bins", type=int, default=20, help="Histogram bins (default: 20)")
    ap.add_argument("--threshold-branches", type=int, default=5, help="Branches threshold for Critical/Warning severity (default: 5)")
    ap.add_argument("--threshold-depth", type=int, default=3, help="Depth threshold for Critical/Warning severity (default: 3)")
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
        threshold_branches=args.threshold_branches,
        threshold_depth=args.threshold_depth,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
