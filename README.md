# Codebase Analysis → Single-file HTML Report

This project converts a `analysis_report.json` codebase complexity report into a **single self-contained HTML file** (`report.html`) that:

- Works when opened via `file://` (no backend required)
- Tries to use CDN libraries for interactive charts (online mode)
- Falls back gracefully to a usable, offline-friendly UI if CDN loading fails

## Requirements

- Python 3.11+ (stdlib only; no third-party dependencies)

## Quick start

Generate the report:

```bash
python3 codebase_analysis_html_report.py --input analysis_report.json --output report.html
```

Open `report.html` in any browser.

## Makefile workflow

```bash
make report
make test
make clean
```

You can override paths:

```bash
make report INPUT=analysis_report.json OUTPUT=report.html
```

## Input JSON format

The script reads a JSON file with the following structure:

```json
{
  "summary": {
    "total_files": 3,
    "total_branches": 42,
    "duplicates": {
      "a1b2c3d4e5f6...": [
        "src/Utils/Helper.php",
        "lib/legacy/Helper.php"
      ]
    }
  },
  "files": {
    "src/Auth/Login.php": {
      "checksum": "a1b2c3d4e5f6...",
      "total_branches": 18,
      "max_depth": 5,
      "branches": [
        { "type": "if", "line": 32, "depth": 1, "condition": "$user !== null" },
        { "type": "foreach", "line": 47, "depth": 2, "condition": "$roles as $role" },
        { "type": "match", "line": 61, "depth": 3, "condition": "$role" }
      ],
      "functions": [
        { "name": "authenticate", "line": 10 },
        { "name": "validate", "line": 55 }
      ]
    },
    "src/Order/Checkout.php": {
      "total_branches": 14,
      "max_depth": 4,
      "branches": [
        { "type": "if", "line": 20, "depth": 1, "condition": "$cart->isEmpty()" }
      ],
      "functions": [
        { "name": "process", "line": 15 }
      ]
    },
    "src/Utils/Helper.php": {
      "total_branches": 10,
      "max_depth": 2,
      "branches": [],
      "functions": []
    }
  }
}
```

**Field reference:**

| Field | Required | Description |
|---|---|---|
| `summary.total_files` | No | Overrides the computed file count |
| `summary.total_branches` | No | Overrides the computed branch sum |
| `summary.duplicates` | No | Map of checksum → list of duplicate file paths |
| `files.<path>.checksum` | No | SHA-256 checksum of the file |
| `files.<path>.total_branches` | Yes | Total branch count for the file |
| `files.<path>.max_depth` | Yes | Maximum nesting depth in the file |
| `files.<path>.branches` | No | Per-branch details shown in the Selection panel |
| `files.<path>.functions` | No | Function list shown in the Selection panel |

`branches`, `functions`, `checksum`, and `summary.duplicates` are optional — without them the file still appears in all tables,
hotspot lists, and the directory tree; only the detail panel will show "Full details not embedded".
When `summary.duplicates` is present, the report shows a dedicated **Duplicate Files** section with expandable groups,
a `DUP ×N` badge on each duplicated file in the file table, and a Duplicates chart tab.

## CLI usage

```bash
python3 codebase_analysis_html_report.py \
  --input analysis_report.json \
  --output report.html \
  --top 20 \
  --max-details 50 \
  --bins 20
```

Arguments:

| Argument | Default | Description |
|---|---|---|
| `--input` | `analysis_report.json` | Input JSON report path |
| `--output` | `report.html` | Output HTML path |
| `--top` | `20` | Top N hotspot files to show in the Hotspots section |
| `--max-details` | `50` | Embed full branch/function detail for up to M hottest files |
| `--bins` | `20` | Histogram bin count for the distribution charts |

## Detailed usage examples

### Example 1: Minimal report for quick sharing

Embed details for fewer files to keep the HTML smaller and faster to open:

```bash
python3 codebase_analysis_html_report.py \
  --input analysis_report.json \
  --output report-small.html \
  --top 10 \
  --max-details 10 \
  --bins 10
```

What this produces:
- Hotspot tables list the 10 highest-branch and 10 highest-depth files
- Clicking a file in the top 10 shows its full branch/function detail panel
- Clicking any other file shows a summary-only panel ("Full details not embedded")
- Charts use 10 histogram bins (coarser distribution view)

### Example 2: Rich drill-down for code review

When you want file click-through to work for many more files (at the cost of a larger HTML):

```bash
python3 codebase_analysis_html_report.py \
  --input analysis_report.json \
  --output report-full.html \
  --top 50 \
  --max-details 500 \
  --bins 30
```

What this produces:
- The Hotspots section lists the 50 most complex files
- The detail panel shows branch-by-branch information for up to 500 files
- 30-bin histograms give a finer view of complexity distribution

### Example 3: Offline-first / air-gapped viewing

The report is fully usable without a network connection:

1. Generate `report.html` on a machine with internet access (or without — the generator never fetches anything):
   ```bash
   python3 codebase_analysis_html_report.py --input analysis_report.json --output report.html
   ```
2. Transfer `report.html` to the air-gapped machine (USB, email, etc.)
3. Open `report.html` via `file://` in any browser

Expected behavior when offline:
- An "Offline fallback mode" banner appears at the top
- The Plotly charts panel shows placeholder messages instead of interactive charts
- All tables, the directory drill-down tree, and the selection detail panel work normally (pure vanilla JS, no CDN required)

To retry loading CDN charts after regaining connectivity, click **Retry online** in the banner.

### Example 4: Rename the output and open immediately (macOS)

```bash
python3 codebase_analysis_html_report.py \
  --input analysis_report.json \
  --output complexity-$(date +%Y%m%d).html

open complexity-$(date +%Y%m%d).html
```

### Example 5: Large codebases (10 000+ files)

The generator avoids loading all files at once in the browser. The tree is lazy-loaded and the
file list is paginated (200 rows at a time with a "Show more" button).

Recommended settings for large repos:

```bash
python3 codebase_analysis_html_report.py \
  --input analysis_report.json \
  --output report.html \
  --top 20 \
  --max-details 50 \
  --bins 20
```

UI tips for large reports:
- Use the **Directory Drill-down** sidebar to navigate subtrees without loading all files
- Click **Expand** / **Collapse** to bulk-open or close tree nodes
- Click **Up** to navigate to the parent directory, **Home** to return to the root
- Directories with a red "danger" risk badge (score ≥ 10) are the highest-priority areas to investigate

### Example 6: Integrate with a PHP static analysis pipeline

A typical workflow where a PHP analyser writes the JSON and this script renders it:

```bash
# Step 1 — run your analyser (example with a hypothetical tool)
php-complexity-scan --format json --output analysis_report.json ./src

# Step 2 — render the HTML report
python3 codebase_analysis_html_report.py \
  --input analysis_report.json \
  --output report.html \
  --top 20 \
  --max-details 100

# Step 3 — open or publish
open report.html
```

As a one-liner in CI (the HTML is a build artifact you can archive):

```bash
php-complexity-scan --format json --output analysis_report.json ./src \
  && python3 codebase_analysis_html_report.py \
       --input analysis_report.json \
       --output report.html
```

### Example 7: Generate a minimal JSON by hand and test the report

You can create a hand-crafted JSON to test the report without running a full analyser:

```bash
cat > sample.json << 'EOF'
{
  "summary": { "total_files": 2, "total_branches": 12 },
  "files": {
    "app/Controller.php": {
      "total_branches": 9, "max_depth": 3,
      "branches": [
        { "type": "if",      "line": 10, "depth": 1, "condition": "$request->isPost()" },
        { "type": "foreach", "line": 20, "depth": 2, "condition": "$items as $item" },
        { "type": "if",      "line": 25, "depth": 3, "condition": "$item->valid()" }
      ],
      "functions": [{ "name": "handle", "line": 5 }]
    },
    "app/Model.php": {
      "total_branches": 3, "max_depth": 1,
      "branches": [
        { "type": "if", "line": 8, "depth": 1, "condition": "$id > 0" }
      ],
      "functions": [{ "name": "find", "line": 3 }]
    }
  }
}
EOF

python3 codebase_analysis_html_report.py --input sample.json --output sample_report.html
open sample_report.html
```

## UI feature overview

| UI element | What it does |
|---|---|
| **Directory Drill-down** (sidebar) | Navigate the directory tree, see per-directory risk scores |
| **Overview** card | Total file and branch counts at a glance |
| **Selection** card | Details for the currently selected file or directory |
| **Hotspots** card | Top files ranked by branch count and by nesting depth |
| **Files** table | Paginated list of all files, sortable by branch/depth |
| **Duplicate Files** card | Expandable table of duplicate file groups (by checksum), with copy count and full paths |
| **Charts** card | Plotly histograms of branch/depth distributions and duplicate file chart (online only) |
| Risk badges | `good` (score < 6), `warn` (6–9), `danger` (≥ 10) — computed per directory |
| `DUP ×N` badge | Purple badge on files that share a checksum with N−1 other files |

## Notes on the directory tree

- The "Directory Drill-down" sidebar contains a lazy `<details>` tree and a summary table.
- Child nodes are only rendered when a node is expanded, keeping initial load fast.
- The tree hides the `valid/` directory branch (hard-coded filter in the embedded JS).
- Up to 200 files are shown per directory node; a "… and N more" message appears if there are more.

## Running tests

```bash
make test
```

## Output artifacts

- `report.html`: single-file HTML report output
