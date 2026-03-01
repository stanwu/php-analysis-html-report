You are a senior Python engineer and data-visualization architect.

Goal
Build a Python tool that converts an existing codebase analysis JSON report into a SINGLE-FILE static HTML5 report (one .html file) that supports BOTH:
- Online mode (preferred): loads JS libraries from CDN for charts/tree
- Offline mode (fallback): still opens and provides essential insights without requiring external fetches (but interactive charts/tree may be limited if CDN is unavailable)

Input
- One JSON file: analysis_report.json
- The JSON contains overall metrics (e.g., total_files, most_complex) and per-file items including:
  - file path
  - total_branches
  - max_depth
  - functions and branches details

Hard Constraints
- Output must be ONE HTML file only (e.g., report.html). No extra JS/CSS/data files.
- Must NOT attempt to render all ~14k files as one giant tree at initial load.
- Must remain usable when opened directly via file:// (no backend).
- CDN is allowed for enhanced interactivity, but the report must still display essential summaries offline if CDN fails (graceful degradation).
- Keep Python dependencies minimal. No API keys. No external services.

Key UX Requirements
1) Fast initial load:
   - Do not compute heavy aggregations fully in the browser at load time.
   - Precompute summary/aggregations in Python and embed them in HTML.
2) Tree/hierarchy:
   - Provide a directory-level hierarchy view (tree or treemap) that initially shows only 1–2 levels.
   - Drill-down should not render all files at once. Use:
     - directory drill-down panels generated from precomputed aggregates, OR
     - search + filtered lists to reach file details.
3) Search:
   - Client-side search for file paths (typeahead) using an embedded index.
4) Filters:
   - Threshold filters for max_depth and total_branches (client-side).

Offline/Online Behavior
- Online mode:
  - Use CDN libraries (allowed) for interactive charts/tree (e.g., Plotly + D3).
- Offline fallback:
  - If CDN scripts fail to load, show:
    - A clear banner: “Offline fallback mode: interactive charts may be unavailable.”
    - Essential summaries as plain HTML tables (hotspots, directory aggregates, distributions as textual buckets).
  - The page must not be blank or broken offline.

Data Strategy (Critical)
Since there are ~14k files:
- Embed the original raw JSON in the HTML (optional; only if size is acceptable), OR embed only the needed detail slices.
- MUST embed precomputed structures to avoid heavy browser work:
  A) overview:
     - total_files
     - top hotspots by total_branches (Top N)
     - top hotspots by max_depth (Top N)
     - distribution buckets for total_branches and max_depth (hist bins computed in Python)
     - Pareto summary (optional)
  B) directory aggregates:
     - aggregated stats per directory node:
       - file_count
       - total_branches_sum, total_branches_avg
       - max_depth_max
       - top_hotspots (Top N)
     - hierarchy adjacency: parent -> children (directories only)
  C) file index:
     - file_id -> path + key metrics
     - search index for paths (simple array or prefix map; must be compact)
  D) file details (optional / limited):
     - For Top hotspots only (recommended), embed full function/branch detail.
     - For all other files, embed only summary metrics, to keep HTML size manageable.

Deliverables
1) A Python CLI script that:
   - Reads analysis_report.json
   - Computes overview stats, directory aggregates, and search index
   - Writes a single output file report.html (ONLY ONE file)
2) The report.html must include:
   - Embedded data (JSON inside <script type="application/json"> blocks)
   - Inline CSS (or minimal inline styles)
   - Inline JS that:
     - loads CDN libraries when online
     - detects CDN load failures and switches to offline fallback UI
3) Clear CLI arguments:
   - --input PATH (default: analysis_report.json)
   - --output PATH (default: report.html)
   - --top N (default: 20)
   - --max-details M (how many files to embed full details for; default: 50)
   - --bins K (histogram bins; default: 20)

Visualization Requirements (Online Mode)
- Dashboard:
  - Histogram of total_branches distribution
  - Histogram of max_depth distribution
  - Bar chart: Top N hotspots by total_branches
  - Bar chart: Top N hotspots by max_depth
- Hierarchy:
  - Directory treemap or collapsible tree (directories only), initial depth 1–2
- Detail panels:
  - Clicking a directory shows its aggregated summary and top hotspots
  - Clicking a file shows summary metrics + (if available) functions/branches

Offline Fallback Requirements
When CDN libraries are unavailable:
- Show:
  - Hotspots tables (Top N)
  - Directory risk table (Top directories sorted by risk metric)
  - Distribution as precomputed bins displayed as tables or simple ASCII bars
  - Search + filters still work (vanilla JS only)

Implementation Guidance
- Python 3.11+
- Use Jinja2 OR simple string templates (keep minimal)
- Avoid heavy browser computation; do aggregation in Python.
- Risk metric suggestion:
  - score = w1 * log1p(total_branches_sum) + w2 * max_depth_max + w3 * file_count
  - choose reasonable defaults and document them

Now produce:
1) Proposed architecture for the single-file HTML (sections + embedded data blocks + JS init flow)
2) Data models for:
   - overview
   - directory aggregates + hierarchy
   - file index
   - file details (limited)
3) Full Python code for the CLI script (production-quality: robust parsing, error handling)
4) The complete report.html template (single file output), including:
   - CDN script tags
   - fallback detection logic
   - offline-mode rendering
5) Brief usage instructions (how to open online and offline)
Important: Do NOT render all files as one tree. Do NOT require a backend.

