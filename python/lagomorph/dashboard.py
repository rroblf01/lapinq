from __future__ import annotations

from typing import Any

from starlette.responses import HTMLResponse

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f3f4f6;
    color: #1f2937;
    min-height: 100vh;
}
.container { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }

.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }
.header h1 { font-size: 1.75rem; font-weight: 700; }
.header h1 small { font-size: 0.875rem; font-weight: 400; color: #6b7280; margin-left: 0.5rem; }

.filters { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.filter-group { display: inline-flex; align-items: center; gap: 0.25rem; white-space: nowrap; }
.filter-group label { font-size: 0.8125rem; color: #6b7280; }
.filters select, .filters input {
    padding: 0.375rem 0.625rem;
    border: 1px solid #d1d5db;
    border-radius: 0.375rem;
    font-size: 0.8125rem;
    background: #fff;
    color: #1f2937;
    outline: none;
    transition: border-color 0.15s;
}
.filters select:focus, .filters input:focus { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,0.15); }

.cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.card {
    background: #fff;
    border-radius: 0.75rem;
    padding: 1.25rem;
    border: 1px solid #e5e7eb;
}
.card-name { font-size: 0.8125rem; color: #6b7280; margin-bottom: 0.25rem; }
.card-count { font-size: 1.5rem; font-weight: 700; }
.card-stats { display: flex; gap: 1rem; margin-top: 0.75rem; font-size: 0.8125rem; flex-wrap: wrap; }
.card-stats .c-pending { color: #ca8a04; }
.card-stats .c-running { color: #2563eb; }
.card-stats .c-done    { color: #16a34a; }
.card-stats .c-failed  { color: #dc2626; }
.card-stats span { white-space: nowrap; }
.card-stats .num { font-weight: 600; }

.table-wrap {
    background: #fff;
    border-radius: 0.75rem;
    border: 1px solid #e5e7eb;
    overflow: hidden;
}
.table-header {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid #e5e7eb;
    font-size: 1rem;
    font-weight: 600;
}
table { width: 100%; border-collapse: collapse; }
th {
    text-align: left;
    font-size: 0.6875rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #e5e7eb;
    background: #f9fafb;
}
td {
    padding: 0.75rem 1rem;
    font-size: 0.8125rem;
    border-bottom: 1px solid #f3f4f6;
    color: #4b5563;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f9fafb; }
td.name { color: #1f2937; font-weight: 500; }
td.mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; color: #6b7280; }
td.trunc { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
td.err { color: #dc2626; }

.badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    font-size: 0.6875rem;
    font-weight: 600;
    border-radius: 9999px;
    text-transform: capitalize;
}
.badge-pending   { color: #ca8a04; background: #fef9e7; }
.badge-running   { color: #2563eb; background: #eef2ff; }
.badge-completed { color: #16a34a; background: #ecfdf5; }
.badge-failed    { color: #dc2626; background: #fef2f2; }

.empty { padding: 1.5rem; text-align: center; color: #9ca3af; }
.connecting { padding: 1.5rem; text-align: center; color: #9ca3af; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.skeleton {
    background: #fff;
    border-radius: 0.75rem;
    padding: 1.25rem;
    border: 1px solid #e5e7eb;
    animation: pulse 2s ease-in-out infinite;
}
.skeleton .line { height: 0.75rem; background: #e5e7eb; border-radius: 0.25rem; margin-bottom: 0.75rem; }
.skeleton .line:last-child { margin-bottom: 0; }
.skeleton .w-24 { width: 6rem; }
.skeleton .w-32 { width: 8rem; }
"""


def dashboard_page(stats: list[dict[str, Any]] | None = None) -> HTMLResponse:
    queues = sorted({s["queue_name"] for s in (stats or [])})
    options = "<option value=''>All queues</option>"
    for q in queues:
        options += f"<option value='{q}'>{q}</option>"

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lagomorph Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Lagomorph <small>Dashboard</small></h1>
    </div>
    <div class="filters">
      <span class="filter-group"><label for="queue-filter">Queue:</label>
      <select id="queue-filter" onchange="setFilter('queue',this.value)">{options}</select></span>
      <span class="filter-group"><label for="status-filter">Status:</label>
      <select id="status-filter" onchange="setFilter('status',this.value)">
        <option value="">All</option>
        <option value="pending">Pending</option>
        <option value="running">Running</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
      </select></span>
      <span class="filter-group"><label for="id-filter">ID:</label>
      <input id="id-filter" type="text" placeholder="Task ID..." oninput="setFilter('id',this.value)"></span>
      <span class="filter-group"><label for="args-filter">Args:</label>
      <input id="args-filter" type="text" placeholder="Search args..." oninput="setFilter('args',this.value)"></span>
      <span class="filter-group"><label for="result-filter">Result:</label>
      <input id="result-filter" type="text" placeholder="Search result..." oninput="setFilter('result',this.value)"></span>
      <span class="filter-group"><label for="error-filter">Error:</label>
      <input id="error-filter" type="text" placeholder="Search error..." oninput="setFilter('error',this.value)"></span>
    </div>
  </div>

  <div id="queue-cards" class="cards-grid">
    <div class="skeleton"><div class="line w-24"></div><div class="line w-32"></div></div>
  </div>

  <div class="table-wrap">
    <div class="table-header">Recent Tasks</div>
    <div id="tasks-table">
      <div class="connecting">Connecting...</div>
    </div>
  </div>
</div>

<script>
let ws;
function connect() {{
    ws = new WebSocket("ws://" + location.host + "/ws");
    ws.onmessage = function(e) {{
        var data = JSON.parse(e.data);
        if (data.cards) document.getElementById("queue-cards").innerHTML = data.cards;
        if (data.table) document.getElementById("tasks-table").innerHTML = data.table;
    }};
    ws.onclose = function() {{ setTimeout(connect, 1000); }};
}}
function setFilter(type, value) {{
    if (ws && ws.readyState === WebSocket.OPEN) {{
        var msg = {{}};
        msg[type] = value.trim();
        ws.send(JSON.stringify(msg));
    }}
}}
connect();
</script>
</body>
</html>""",
        media_type="text/html",
    )


def queues_html(stats: list[dict[str, Any]]) -> HTMLResponse:
    return HTMLResponse(_queue_cards_html(stats), media_type="text/html")


def tasks_html(tasks: list[dict[str, Any]]) -> HTMLResponse:
    return HTMLResponse(_tasks_table_html(tasks), media_type="text/html")


def _queue_cards_html(stats: list[dict[str, Any]]) -> str:
    if not stats:
        return '<div class="empty" style="grid-column:1/-1">No queues yet</div>'

    cards = ""
    for q in stats:
        total = q["pending"] + q["running"]
        cards += f"""
        <div class="card">
            <div class="card-name">{q["queue_name"]}</div>
            <div class="card-count">{total} active</div>
            <div class="card-stats">
                <span class="c-pending"><span class="num">{q["pending"]}</span> pending</span>
                <span class="c-running"><span class="num">{q["running"]}</span> running</span>
                <span class="c-done"><span class="num">{q["completed"]}</span> done</span>
                <span class="c-failed"><span class="num">{q["failed"]}</span> failed</span>
            </div>
        </div>"""
    return cards


def _tasks_table_html(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return '<div class="empty">No tasks found</div>'

    def _fmt(val: Any, maxlen: int = 60) -> str:
        if val is None:
            return ""
        s = str(val)
        return s[:maxlen] + "..." if len(s) > maxlen else s

    def _args_str(t: dict[str, Any]) -> str:
        parts = []
        if t.get("args"):
            parts.append(", ".join(str(a) for a in t["args"]))
        if t.get("kwargs"):
            parts.append(", ".join(f"{k}={v}" for k, v in t["kwargs"].items()))
        return ", ".join(parts)

    rows = ""
    for t in tasks:
        tid = str(t.get("id", ""))[:8]
        status = t.get("status", "unknown")
        badge = f"badge-{status}" if status in ("pending", "running", "completed", "failed") else "badge-pending"

        args_str = _args_str(t)
        result_val = t.get("result")
        error_val = t.get("error")

        rows += f"""
        <tr>
            <td class="mono">{tid}...</td>
            <td class="name">{t.get("task_name", "")}</td>
            <td>{t.get("queue_name", "")}</td>
            <td class="trunc" title="{args_str}">{_fmt(args_str)}</td>
            <td class="trunc" title="{result_val or ""}">{_fmt(result_val)}</td>
            <td class="trunc err" title="{error_val or ""}">{_fmt(error_val)}</td>
            <td><span class="badge {badge}">{status}</span></td>
        </tr>"""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Task</th>
                <th>Queue</th>
                <th>Args</th>
                <th>Result</th>
                <th>Error</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""
