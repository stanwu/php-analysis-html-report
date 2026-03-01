# Codebase Analysis HTML Report — Comprehensive Implementation Prompt

You are a senior Python engineer and data-visualization architect.

## Goal

Build a Python CLI script `codebase_analysis_html_report.py` that converts a codebase analysis JSON file into a **single-file static HTML5 report** (`report.html`).

- **Online mode**: loads Plotly from CDN for interactive charts.
- **Offline mode**: graceful fallback — tables, search, and filters remain fully functional without CDN.

---

## Input JSON Format

File: `analysis_report.json`

```json
{
  "summary": {
    "total_files": 14000,
    "total_branches": 98000
  },
  "files": {
    "src/Foo/Bar.php": {
      "total_branches": 42,
      "max_depth": 5,
      "branches": [
        {"type": "if", "line": 12, "depth": 1, "condition": "$x > 0"},
        {"type": "foreach", "line": 20, "depth": 2, "condition": null}
      ],
      "functions": [
        {"name": "processOrder", "total_branches": 30, "max_depth": 4},
        {"name": "validate", "total_branches": 12, "max_depth": 2}
      ]
    }
  }
}
```

---

## Hard Constraints

- Output is **one HTML file only** — no external CSS/JS/data files.
- Must work via `file://` with no backend.
- CDN allowed for charts; degrade gracefully without it.
- Python 3.11+. No API keys. No heavy dependencies (use stdlib + optional Jinja2).

---

## CLI Arguments

```
python codebase_analysis_html_report.py [options]

--input PATH              Input JSON (default: analysis_report.json)
--output PATH             Output HTML (default: report.html)
--top N                   Top N hotspots (default: 20)
--max-details M           Embed full branch/function detail for top M files (default: 50)
--bins K                  Histogram bins (default: 20)
--threshold-branches INT  Branches threshold for severity (default: 5)
--threshold-depth INT     Depth threshold for severity (default: 3)
```

---

## Python Helper Functions

### Utilities

```python
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _json_dumps_for_html(obj) -> str:
    # Escape </script> injection risk
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

def _norm_path(path: str) -> str:
    # Normalize to forward-slash paths
    return str(PurePosixPath(path.replace("\\", "/")))

def _dir_ancestors(file_path: str) -> list[str]:
    # Returns ["", "src", "src/Foo"] for "src/Foo/Bar.php"
    p = PurePosixPath(file_path)
    parts = list(p.parts)
    if len(parts) <= 1:
        return [""]
    dirs = [""]
    for i in range(1, len(parts)):
        dirs.append("/".join(parts[:i]))
    return dirs

def _safe_int(v, default=0) -> int:
    try:
        return default if v is None else int(v)
    except Exception:
        return default
```

### Risk Score

```python
def _risk_score(total_branches_sum: int, max_depth_max: int, file_count: int) -> float:
    w1, w2, w3 = 1.5, 2.0, 0.1
    return w1 * math.log1p(total_branches_sum) + w2 * max_depth_max + w3 * file_count
```

### Histogram

```python
def _compute_equal_width_hist(values: list[int], bins: int) -> dict:
    # Returns: {"min": int, "max": int, "bins": [{"lo": int, "hi": int, "count": int, "label": "lo–hi"}, ...]}
    # Handles empty list and all-same-value edge cases.
```

---

## Data Structures (Embedded as JSON in HTML)

### 1. `dataOverview` (`<script type="application/json" id="dataOverview">`)

```json
{
  "generated_at": "2024-01-01T00:00:00+00:00",
  "input": "analysis_report.json",
  "total_files": 14000,
  "total_branches": 98000,
  "max_depth_overall": 12,
  "threshold_branches": 5,
  "threshold_depth": 3,
  "over_threshold": {"branches": 3200, "depth": 870},
  "top_modules": [
    {"dir": "src/Commerce", "score": 45.2, "file_count": 120}
  ],
  "hotspots": {
    "by_branches": [
      {"rank": 1, "path": "src/Foo/Bar.php", "total_branches": 42, "max_depth": 5, "pct_branches": 0.04}
    ],
    "by_depth": [...]
  },
  "distributions": {
    "total_branches": {"min": 0, "max": 200, "bins": [{"lo": 0, "hi": 10, "count": 5000, "label": "0–10"}, ...]},
    "max_depth": {"min": 0, "max": 12, "bins": [...]}
  }
}
```

- `top_modules`: top 3 non-root dirs sorted by `score` descending.
- `hotspots.by_branches`: top N files sorted by `(-total_branches, -max_depth, path)`.
- `hotspots.by_depth`: top N files sorted by `(-max_depth, -total_branches, path)`.
- `pct_branches`: `round(f.total_branches / max(total_branches, 1) * 100, 1)`.

### 2. `dataDirs` (`<script type="application/json" id="dataDirs">`)

```json
{
  "root": "",
  "nodes": {
    "": {"file_count": 14000, "total_branches_sum": 98000, "total_branches_avg": 7.0, "max_depth_max": 12, "score": 89.5, "top_files": [0, 5, 12]},
    "src": {...},
    "src/Foo": {...}
  },
  "children": {
    "": ["src", "tests"],
    "src": ["src/Foo", "src/Bar"]
  },
  "files": {
    "": [0, 1, 2],
    "src/Foo": [3, 7]
  }
}
```

- `nodes[dir].top_files`: list of `file_id` integers, up to `max(5, min(50, top_n))` per dir, sorted by `(-total_branches, -max_depth, path)`.
- `children[dir]`: sorted list of immediate child directory paths.
- `files[dir]`: file IDs directly in that directory (not subdirs), sorted by path.
- Root directory is always `""`.

### 3. `dataFiles` (`<script type="application/json" id="dataFiles">`)

```json
{
  "files": [
    {"id": 0, "path": "src/Foo/Bar.php", "b": 42, "d": 5},
    {"id": 1, "path": "src/Foo/Baz.php", "b": 10, "d": 2}
  ]
}
```

- Files sorted by normalized path (`sorted(files_raw.keys(), key=lambda p: _norm_path(str(p)))`).
- `id` is a sequential integer starting from 0.
- Keys `b` = `total_branches`, `d` = `max_depth` (short for compactness).

### 4. `dataDetails` (`<script type="application/json" id="dataDetails">`)

```json
{
  "details": {
    "0": {
      "branches": [{"type": "if", "line": 12, "depth": 1, "condition": "$x > 0"}],
      "functions": [{"name": "processOrder", "total_branches": 30, "max_depth": 4}]
    }
  }
}
```

- Only top `max_details` hottest files (sorted by `(-total_branches, -max_depth, path)`) have entries.
- Keys are `file_id` as string (JSON object keys must be strings).
- `branches` and `functions` are taken directly from the raw JSON (`item.get("branches") or []`, `item.get("functions") or []`).

---

## HTML Structure

Single-file HTML with:
- Inline CSS with CSS custom properties (variables)
- 4 `<script type="application/json">` data blocks
- One `<script>` with all JS logic

### Layout

```
<div class="app">  <!-- CSS grid: 300px sidebar | 1fr main -->
  <aside class="navpane">  <!-- sticky, 100vh, scrollable -->
    Directory Filter sidebar
  </aside>
  <div class="main">
    <div class="wrap">  <!-- max-width: 1280px, centered -->
      Header (title + KPIs)
      Status bar
      Offline banner (hidden when online)
      Controls bar (search + filters)
      File list card
      Charts card
      Footer
    </div>
  </div>
</div>
```

Responsive breakpoint at `900px`: grid becomes 1 column, sidebar is static.

---

## CSS Design System

Use CSS custom properties:

```css
:root {
  --bg: #f6f7fb;
  --panel: #ffffff;
  --panel2: #f8fafc;
  --text: #0f172a;
  --muted: #475569;
  --border: #e2e8f0;
  --accent: #2563eb;
  --danger: #e11d48;
  --good: #059669;
  --warn: #b45309;
  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
}
```

Key component classes:
- `.badge.good / .warn / .danger` — pill badges with colored border + background
- `.section-card` — white card with border, border-radius 12px, subtle box-shadow
- `.file-table` — full-width, sticky thead, hover rows
- `.mono` — applies `var(--mono)` font
- `.hidden` — `display: none`
- `.btn` — neutral button style

---

## JavaScript Architecture

### Data Initialization

```js
const overview = parseJsonScript("dataOverview");
const dirsData = parseJsonScript("dataDirs");
const filesData = parseJsonScript("dataFiles");
const detailsData = parseJsonScript("dataDetails");

const files = filesData.files || [];
const fileById = new Map(files.map(f => [f.id, f]));
const dirNodes = dirsData.nodes || {};
const dirChildren = dirsData.children || {};
const rootDir = dirsData.root !== undefined ? dirsData.root : "";

const TB = overview.threshold_branches || 5;
const TD = overview.threshold_depth || 3;
const totalBranches = overview.total_branches || 1;
```

### Global State

```js
let hasPlotly = false;
let fileListLimit = 200;        // pagination: show 200 at a time
let searchQuery = "";
let filterBranchesMin = 0;
let filterDepthMin = 0;
let filterSev = "all";          // "all" | "danger" | "warn" | "good"
let filterDir = null;           // null = all, "" = root, "src/Foo" = specific dir
let wired = false;
const expandedFiles = new Set();
```

### Severity Logic

```js
function getSeverity(b, d) {
  if (b > TB * 2 || d > TD * 2) return "danger";
  if (b > TB || d > TD) return "warn";
  return "good";
}

function getDepthClass(depth) {
  if (depth >= TD * 1.5) return "danger";
  if (depth >= TD) return "warn";
  return "ok";
}
```

### File Filtering

```js
function getFilteredFiles() {
  return files.filter(f => {
    if (searchQuery && !f.path.toLowerCase().includes(searchQuery)) return false;
    if (filterBranchesMin > 0 && f.b < filterBranchesMin) return false;
    if (filterDepthMin > 0 && f.d < filterDepthMin) return false;
    if (filterDir !== null && filterDir !== "") {
      if (!f.path.startsWith(filterDir + "/")) return false;
    }
    if (filterSev !== "all" && getSeverity(f.b, f.d) !== filterSev) return false;
    return true;
  }).sort((a, b) => (b.b - a.b) || (b.d - a.d) || a.path.localeCompare(b.path));
}
```

### File Table

- Renders up to `fileListLimit` rows from filtered results.
- Columns: `Rank`, `File` (mono path), `Branches`, `Depth`, `Impact (% of total branches)`, `Severity badge`.
- First file gets a `START` badge (blue pill).
- Each row has an expand arrow (`▶`, rotates to point down when expanded).
- Clicking a row toggles an inline detail row (lazy-rendered on first open).
- "Show more" button increments `fileListLimit` by 200; disabled when all shown.
- Impact footer: "Refactoring top N files eliminates X% of total branch complexity."

### Expand-in-Place Detail Row

When expanded, shows a 2-column grid:
1. **Functions panel** — sortable table (`Function`, `Branches`, `Depth`, `% of file`); insight box if top function is ≥50% of file complexity.
2. **Branch detail panel** — list with depth-based indentation (`depth * 14px`), type/line/condition/depth badge.

If file is not in `dataDetails`, show: "Details not embedded for this file (outside top max-details). Summary: branches=X, max_depth=Y"

### Directory Sidebar Tree

- Root entry "(all files)" with file count; click clears filter.
- Child nodes built lazily (on `<details>` toggle).
- Each dir node shows: name (mono), file count, risk score badge.
- Clicking a dir node sets `filterDir` and re-renders file table.
- Active filter shown as a breadcrumb above the tree with an `×` clear button.

### Controls Bar

- Text search (`id="searchInput"`) — filters by path substring (case-insensitive).
- Branches ≥ number input — filters by `f.b >= value`.
- Depth ≥ number input — filters by `f.d >= value`.
- Severity buttons: `All` | `🔴 Critical` | `🟡 Warning` | `🟢 OK` (one active at a time).
- `Ctrl+F` / `Cmd+F` focuses search input (preventDefault on default browser search).
- Any filter change resets `fileListLimit = 200`.

### Charts (Plotly — Online Mode)

CDN URL: `https://cdn.plot.ly/plotly-2.30.0.min.js` with 4500ms timeout.

Load with:
```js
function loadScript(src, ms) {
  return new Promise((res, rej) => {
    const s = document.createElement("script"), t = setTimeout(() => rej(), ms || 4500);
    s.src = src; s.async = true;
    s.onload = () => { clearTimeout(t); res(); };
    s.onerror = () => { clearTimeout(t); rej(); };
    document.head.appendChild(s);
  });
}
```

Four charts (tab-switched):
1. **Directory map** (tab: `treemap`) — Plotly treemap of all dirs; colors: danger=`rgba(225,29,72,.65)`, warn=`rgba(251,191,36,.65)`, good=`rgba(5,150,105,.55)`.
2. **Branches dist.** (tab: `branches`) — Bar chart, top 5 bins by count, color `rgba(96,165,250,.75)`.
3. **Depth dist.** (tab: `depth`) — Bar chart, top 5 bins by count, color `rgba(52,211,153,.75)`.
4. **Hotspots** (tab: `hotspots`) — Horizontal bar, top 5 files by branches, color `rgba(251,191,36,.75)`. **Default active tab.**

Tab layout: pill-style tabs, only one chart `div` visible at a time (`.hidden` class toggle).

Chart layout common settings:
```js
const gridColor = "rgba(226,232,240,1)";
const axisCommon = { tickangle: -30, gridcolor: gridColor, zerolinecolor: gridColor, linecolor: "rgba(203,213,225,1)", tickfont: { color: "#0f172a" } };
const layout0 = { margin: {l:40, r:10, t:36, b:80}, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: "#0f172a" } };
```

All charts: `displayModeBar: false, responsive: true`.

### Offline Mode

- `hasPlotly = false` → show offline banner (red border, retry button).
- Chart divs show: "Offline fallback: chart unavailable."
- All tables, search, and filters remain functional (pure vanilla JS).
- Mode pill badge: green "Online mode" or red "Offline fallback".

### Init Flow

```js
async function init(forceTryOnline) {
  initMeta();
  if (!wired) { wireTabs(); wireControls(); wired = true; }
  renderStatusBar();
  renderDirTree();
  renderFileTable();
  if (forceTryOnline) {
    try { await loadScript(...); hasPlotly = !!window.Plotly; }
    catch (e) { hasPlotly = false; }
  }
  setMode(hasPlotly);
  renderOfflineDistributions();
  renderChartsOnline();
}

init(true);
```

"Retry online" button calls `init(true)`.

---

## Status Bar

Below the header, shows:
- `🔴 N critical (branches > TB)` — if `over_threshold.branches > 0`
- `🟡 N deep (depth > TD)` — if `over_threshold.depth > 0`
- `🟢 All files within threshold` — if both are 0
- Top hotspot module names with their risk scores

---

## Python `build_report` Function

```python
def build_report(input_path, output_path, top_n, max_details, bins, threshold_branches=5, threshold_depth=3):
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    summary = raw.get("summary") or {}
    files_raw = raw.get("files") or {}

    # 1. Build FileSummary list (sorted by normalized path)
    # 2. Compute total_files, total_branches, max_depth_overall
    # 3. Build hotspots (by_branches, by_depth)
    # 4. Compute histograms (equal-width bins)
    # 5. Build directory aggregates:
    #    - For each file, call _dir_ancestors() and accumulate into dir_aggs
    #    - TOP_FILES_PER_DIR = max(5, min(50, top_n))
    # 6. Build dir_nodes with score, sort top_files per dir
    # 7. Build hierarchy children dict (sorted) and dir_files dict
    # 8. Build files_index [{id, path, b, d}]
    # 9. Build details for top max_details files
    # 10. Assemble overview_obj, dirs_obj, files_obj, details_obj
    # 11. Template substitution into HTML_TEMPLATE
    # 12. Write to output_path
```

The HTML template uses `{{TITLE}}`, `{{DATA_OVERVIEW}}`, `{{DATA_DIRS}}`, `{{DATA_FILES}}`, `{{DATA_DETAILS}}` as placeholders replaced via Python `.replace()`.

---

## `main()` Function

```python
def main(argv=None) -> int:
    # argparse setup with all 7 arguments listed above
    # Validate input_path.exists()
    # Call build_report(...)
    # Return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

---

## Key Implementation Notes

1. **XSS prevention**: use `_json_dumps_for_html` (escapes `</` → `<\/`) for all embedded JSON.
2. **File ID mapping**: `file_id` = sequential int (0-based); `dataDetails` keys are string representations of IDs (JSON requires string keys).
3. **Lazy sidebar tree**: child dir nodes are only rendered on `<details>` toggle (`det.dataset.loaded` guard).
4. **File detail lazy rendering**: detail cell content is only generated on first expand (`dc.dataset.rendered` guard).
5. **Path normalization**: always use `_norm_path()` for consistency across Windows/Unix paths.
6. **Directory parent lookup**: `d.rsplit("/", 1)[0] if "/" in d else ""` for immediate parent.
7. **`dir_files` vs `dir_nodes.top_files`**: `dir_files[d]` = IDs of files *directly* in `d` (not in subdirs); `dir_nodes[d].top_files` = top hotspot IDs across all files under `d` (including subdirs).
8. **`isFilteredChildDir`** function in JS: originally used to filter out a project-specific directory called "valid" from the sidebar. For a generic implementation, this function can simply return `false` (no filtering).
9. **`escapeHtml`** in JS: replaces `&`, `<`, `>`, `"`, `'` with HTML entities.
10. **Pagination**: file list shows `fileListLimit` (starts at 200) rows; "Show more" adds 200. Button is disabled when all results shown.

---

## Usage

```bash
# Basic
python codebase_analysis_html_report.py

# Custom
python codebase_analysis_html_report.py \
  --input my_report.json \
  --output dashboard.html \
  --top 30 \
  --max-details 100 \
  --bins 15 \
  --threshold-branches 10 \
  --threshold-depth 5

# Open in browser
open report.html          # macOS
xdg-open report.html      # Linux
start report.html         # Windows
```

The report works fully offline for tables/search/filters. Open while connected for interactive Plotly charts.
