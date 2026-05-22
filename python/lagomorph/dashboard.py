from __future__ import annotations

from typing import Any

from starlette.responses import HTMLResponse

dashboard_page = HTMLResponse(
    content="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lagomorph Dashboard</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 dark:bg-gray-900 min-h-screen">
<div class="max-w-6xl mx-auto p-6">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h1 class="text-3xl font-bold text-gray-800 dark:text-white">
        Lagomorph Dashboard
      </h1>
      <p class="text-gray-500 dark:text-gray-400 text-sm mt-1">
        Real-time task queue overview
      </p>
    </div>
    <div class="flex gap-2">
      <button
        hx-get="/api/queues"
        hx-target="#queue-cards"
        hx-trigger="click"
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
      >
        Refresh
      </button>
    </div>
  </div>

  <div hx-get="/api/queues/html" hx-trigger="every 3s" hx-target="#queue-cards" hx-swap="innerHTML">
    <div id="queue-cards" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
      <div class="animate-pulse bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div class="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24 mb-3"></div>
        <div class="h-8 bg-gray-200 dark:bg-gray-700 rounded w-32"></div>
      </div>
    </div>
  </div>

  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
    <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
      <h2 class="text-lg font-semibold text-gray-800 dark:text-white">Recent Tasks</h2>
    </div>
    <div
      hx-get="/api/tasks/html?limit=20"
      hx-trigger="every 3s"
      hx-target="#tasks-table"
      hx-swap="innerHTML"
    >
      <div id="tasks-table" class="overflow-x-auto">
        <div class="p-6 text-center text-gray-400">Loading tasks...</div>
      </div>
    </div>
  </div>

  <div class="mt-8 text-center text-xs text-gray-400">
    Lagomorph v0.1.0 — Auto-refreshes every 3 seconds
  </div>
</div>
</body>
</html>""",
    media_type="text/html",
)


def queues_html(stats: list[dict[str, Any]]) -> HTMLResponse:
    return HTMLResponse(_queue_cards_html(stats), media_type="text/html")


def _queue_cards_html(stats: list[dict[str, Any]]) -> str:
    if not stats:
        return '<div class="col-span-full text-center text-gray-400 py-8">No queues yet</div>'

    cards = ""
    for q in stats:
        total = q["pending"] + q["running"]
        cards += f"""
        <div class="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
            <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">{q["queue_name"]}</div>
            <div class="text-2xl font-bold text-gray-800 dark:text-white">{total} tasks</div>
            <div class="flex gap-4 mt-3 text-sm">
                <span class="text-yellow-600"><span class="font-medium">{q["pending"]}</span> pending</span>
                <span class="text-blue-600"><span class="font-medium">{q["running"]}</span> running</span>
            </div>
        </div>"""
    return cards


def tasks_html(tasks: list[dict[str, Any]]) -> HTMLResponse:
    return HTMLResponse(_tasks_table_html(tasks), media_type="text/html")


def _tasks_table_html(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return '<div class="p-6 text-center text-gray-400">No tasks found</div>'

    rows = ""
    for t in tasks:
        tid = str(t.get("id", ""))[:8]
        status = t.get("status", "unknown")
        status_color = {
            "pending": "text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20",
            "running": "text-blue-600 bg-blue-50 dark:bg-blue-900/20",
            "completed": "text-green-600 bg-green-50 dark:bg-green-900/20",
            "failed": "text-red-600 bg-red-50 dark:bg-red-900/20",
        }.get(status, "text-gray-600 bg-gray-50")

        rows += f"""
        <tr class="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-750">
            <td class="px-6 py-3 text-sm font-mono text-gray-500">{tid}...</td>
            <td class="px-6 py-3 text-sm text-gray-800 dark:text-white">{t.get("task_name", "")}</td>
            <td class="px-6 py-3 text-sm text-gray-500">{t.get("queue_name", "")}</td>
            <td class="px-6 py-3">
                <span class="inline-block px-2 py-0.5 text-xs font-medium rounded-full {status_color}">{status}</span>
            </td>
        </tr>"""
    return f"""
    <table class="w-full">
        <thead>
            <tr class="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
                <th class="px-6 py-3">ID</th>
                <th class="px-6 py-3">Task</th>
                <th class="px-6 py-3">Queue</th>
                <th class="px-6 py-3">Status</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""
