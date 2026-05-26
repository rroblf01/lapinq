from __future__ import annotations

import json as json_module
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
.card-stats .c-cancelled { color: #6b7280; }
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
    display: flex; justify-content: space-between; align-items: center;
}
.load-more { font-size: 0.8125rem; color: #6366f1; cursor: pointer; }
.load-more:hover { text-decoration: underline; }
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
td.actions { white-space: nowrap; }
.btn-action {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    font-size: 0.6875rem;
    border-radius: 0.25rem;
    border: 1px solid #d1d5db;
    background: #fff;
    color: #4b5563;
    cursor: pointer;
    margin-right: 0.25rem;
}
.btn-action:hover { background: #f3f4f6; }
.btn-action.danger { color: #dc2626; border-color: #dc2626; }
.btn-action.danger:hover { background: #fef2f2; }
.btn-delete { color: #dc2626; border-color: #dc2626; font-weight: 600; }
.btn-delete:hover { background: #fef2f2; }

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
.badge-cancelled { color: #6b7280; background: #f3f4f6; }

.empty { padding: 1.5rem; text-align: center; color: #9ca3af; }
.connecting { padding: 1.5rem; text-align: center; color: #9ca3af; }
.cleanup-info { font-size: 0.75rem; color: #9ca3af; margin-bottom: 0.75rem; text-align: right; }

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

.user-bar { display:flex; align-items:center; gap:0.75rem; font-size:0.8125rem; color:#6b7280; }
.user-bar .role-badge { font-size:0.6875rem; padding:0.125rem 0.5rem; border-radius:9999px; font-weight:600; }
.user-bar .role-admin { background:#eef2ff; color:#2563eb; }
.user-bar .role-user  { background:#f3f4f6; color:#6b7280; }
.user-bar a { color:#6366f1; text-decoration:none; }
.user-bar a:hover { text-decoration:underline; }
.user-bar .btn-link { background:none; border:none; color:#6366f1; cursor:pointer; font-size:0.8125rem; padding:0; }
.user-bar .btn-link:hover { text-decoration:underline; }

.modal-overlay {
    display:none; position:fixed; top:0; left:0; width:100%; height:100%;
    background:rgba(0,0,0,0.4); z-index:1000; align-items:center; justify-content:center;
}
.modal-overlay.open { display:flex; }
.modal-box {
    background:#fff; border-radius:0.75rem; padding:1.5rem; width:100%; max-width:420px;
    border:1px solid #e5e7eb; max-height:80vh; overflow-y:auto;
}
.modal-box h2 { font-size:1.125rem; font-weight:600; margin-bottom:1rem; }
.modal-box label { font-size:0.8125rem; font-weight:500; display:block; margin-bottom:0.25rem; }
.modal-box input, .modal-box select {
    width:100%; padding:0.5rem 0.75rem; border:1px solid #d1d5db; border-radius:0.375rem;
    font-size:0.875rem; margin-bottom:0.75rem; outline:none;
}
.modal-box input:focus, .modal-box select:focus { border-color:#6366f1; box-shadow:0 0 0 2px rgba(99,102,241,0.15); }
.modal-box .actions { display:flex; gap:0.5rem; justify-content:flex-end; margin-top:1rem; }
.modal-box button { padding:0.5rem 1rem; border-radius:0.375rem; font-size:0.8125rem; font-weight:600; cursor:pointer; border:1px solid #d1d5db; background:#fff; color:#4b5563; }
.modal-box button.primary { background:#6366f1; color:#fff; border-color:#6366f1; }
.modal-box button.primary:hover { background:#4f46e5; }
.modal-box button:hover { background:#f3f4f6; }
.modal-box .error { color:#dc2626; font-size:0.8125rem; margin-bottom:0.75rem; }

/* Admin users table */
.admin-wrap { max-width:800px; margin:0 auto; padding:1.5rem; }
.admin-wrap h1 { font-size:1.5rem; font-weight:700; margin-bottom:1.5rem; }
.admin-wrap h1 a { font-size:0.875rem; font-weight:400; color:#6366f1; text-decoration:none; margin-left:1rem; }
.admin-wrap table { width:100%; border-collapse:collapse; background:#fff; border-radius:0.75rem; overflow:hidden; border:1px solid #e5e7eb; }
.admin-wrap th { text-align:left; font-size:0.6875rem; color:#6b7280; text-transform:uppercase; letter-spacing:0.05em; padding:0.75rem 1rem; border-bottom:1px solid #e5e7eb; background:#f9fafb; }
.admin-wrap td { padding:0.75rem 1rem; font-size:0.8125rem; border-bottom:1px solid #f3f4f6; color:#4b5563; }
.admin-wrap .btn-sm { padding:0.25rem 0.5rem; font-size:0.6875rem; border-radius:0.25rem; border:1px solid #d1d5db; background:#fff; color:#4b5563; cursor:pointer; margin-right:0.25rem; }
.admin-wrap .btn-sm:hover { background:#f3f4f6; }
.admin-wrap .btn-sm.danger { color:#dc2626; border-color:#dc2626; }
.admin-wrap .btn-sm.danger:hover { background:#fef2f2; }
.admin-wrap .btn-sm.primary { color:#fff; background:#6366f1; border-color:#6366f1; }
.admin-wrap .btn-sm.primary:hover { background:#4f46e5; }
.admin-wrap .create-form { background:#fff; border-radius:0.75rem; padding:1.25rem; border:1px solid #e5e7eb; margin-bottom:1.5rem; display:flex; gap:0.75rem; align-items:flex-end; flex-wrap:wrap; }
.admin-wrap .create-form label { font-size:0.8125rem; font-weight:500; display:block; margin-bottom:0.25rem; }
.admin-wrap .create-form input, .admin-wrap .create-form select { padding:0.5rem 0.75rem; border:1px solid #d1d5db; border-radius:0.375rem; font-size:0.875rem; outline:none; }
.admin-wrap .create-form input:focus, .admin-wrap .create-form select:focus { border-color:#6366f1; }
"""


def _get_session_token() -> str:
    match = __import__("re").search(r'(?:^|;\s*)lapinq_session=([^;]+)', document.cookie)
    return match.group(1) if match else ""


def dashboard_page(
    stats: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    current_user: dict[str, Any] | None = None,
    session_token: str = "",
) -> HTMLResponse:
    queues = sorted({s["queue_name"] for s in (stats or [])})
    options = "<option value=''>All queues</option>"
    for q in queues:
        options += f"<option value='{q}'>{q}</option>"

    user_role = (current_user or {}).get("role", "")
    user_name = (current_user or {}).get("username", "")
    is_admin = user_role == "admin"
    initial_cards = _queue_cards_html(stats or [])
    initial_table = _tasks_table_html(tasks or [])
    initial_user_json = json_module.dumps(current_user or {})

    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lapinq Dashboard</title>
<link rel="icon" href="/favicon.ico" type="image/x-icon">
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Lapinq <small>Dashboard</small></h1>
    </div>
    <div class="user-bar">
      <span class="role-badge role-{user_role}">{user_name} ({user_role})</span>
      <button class="btn-link" onclick="showChangePassword()">Change Password</button>
      {('<a href="/admin/users">Manage Users</a>' if is_admin else '')}
      <a href="/logout">Logout</a>
    </div>
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
      <option value="cancelled">Cancelled</option>
    </select></span>
    <span class="filter-group"><label for="task-name-filter">Task:</label>
    <input id="task-name-filter" type="text" placeholder="Task name..." oninput="setFilter('task_name',this.value)"></span>
    <span class="filter-group"><label for="id-filter">ID:</label>
    <input id="id-filter" type="text" placeholder="Task ID..." oninput="setFilter('id',this.value)"></span>
    <span class="filter-group"><label for="args-filter">Args:</label>
    <input id="args-filter" type="text" placeholder="Search args..." oninput="setFilter('args',this.value)"></span>
    <span class="filter-group"><label for="result-filter">Result:</label>
    <input id="result-filter" type="text" placeholder="Search result..." oninput="setFilter('result',this.value)"></span>
    <span class="filter-group"><label for="error-filter">Error:</label>
    <input id="error-filter" type="text" placeholder="Search error..." oninput="setFilter('error',this.value)"></span>
    <button class="btn-action btn-delete" id="delete-filtered-btn" onclick="deleteFiltered()" {'style="display:none"' if not is_admin else ''}>Delete filtered</button>
  </div>

  <div id="cleanup-info" class="cleanup-info"></div>

  <div id="queue-cards" class="cards-grid">
    {initial_cards}
  </div>

  <div class="table-wrap">
    <div class="table-header">
      <span>Recent Tasks</span>
      <span class="load-more" id="load-more" style="display:none" onclick="loadMore()">Show more &darr;</span>
    </div>
    <div id="tasks-table">
      {initial_table}
    </div>
  </div>
</div>

<div class="modal-overlay" id="change-pw-modal">
  <div class="modal-box">
    <h2>Change Password</h2>
    <div id="change-pw-error" class="error"></div>
    <label for="cp-current">Current Password</label>
    <input id="cp-current" type="password">
    <label for="cp-new">New Password</label>
    <input id="cp-new" type="password">
    <div class="actions">
      <button onclick="closeChangePassword()">Cancel</button>
      <button class="primary" onclick="doChangePassword()">Save</button>
    </div>
  </div>
</div>

<script>
let ws;
let taskOffset = 20;
let currentUser = {initial_user_json};
let sessionToken = "{session_token}";
function connect() {{
    var protocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
    ws = new WebSocket(protocol + location.host + "/ws");
    ws.onopen = function() {{
        ws.send(JSON.stringify({{type:"auth",token:sessionToken}}));
    }};
    ws.onmessage = function(e) {{
        var data = JSON.parse(e.data);
        if (data.cards) document.getElementById("queue-cards").innerHTML = data.cards;
        if (data.table) document.getElementById("tasks-table").innerHTML = data.table;
        if (data.cleanup_interval) document.getElementById("cleanup-info").innerHTML =
            "Cleanup every " + data.cleanup_interval + "s";
        if (data.user) {{
            currentUser = data.user;
            updateUIForRole();
        }}
        taskOffset = 20;
        var lm = document.getElementById("load-more");
        if (lm) lm.style.display = data.has_more ? "inline" : "none";
    }};
    ws.onclose = function() {{ setTimeout(connect, 1000); }};
}}
function updateUIForRole() {{
    var isAdmin = currentUser && currentUser.role === "admin";
    var delBtn = document.getElementById("delete-filtered-btn");
    if (delBtn) delBtn.style.display = isAdmin ? "inline-block" : "none";
}}
function setFilter(type, value) {{
    if (ws && ws.readyState === WebSocket.OPEN) {{
        var msg = {{}};
        msg[type] = value.trim();
        ws.send(JSON.stringify(msg));
    }}
}}
function confirmAction(taskId, action) {{
    if (!confirm("Are you sure you want to " + action + " task " + taskId.substr(0,8) + "...?")) return;
    var method = action === "cancel" ? "DELETE" : "POST";
    var url = "/api/v1/tasks/" + taskId + (action === "requeue" ? "/requeue" : "");
    fetch(url, {{ method: method }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
            if (data.error) alert("Error: " + data.error);
        }})
        .catch(function(err) {{ alert("Request failed: " + err); }});
}}
function deleteFiltered() {{
    if (!confirm("Delete all tasks matching current filters?")) return;
    var params = [];
    var queue = document.getElementById("queue-filter").value;
    if (queue) params.push("queue=" + encodeURIComponent(queue));
    var status = document.getElementById("status-filter").value;
    if (status) params.push("status=" + encodeURIComponent(status));
    var taskName = document.getElementById("task-name-filter").value.trim();
    if (taskName) params.push("task_name=" + encodeURIComponent(taskName));
    var args = document.getElementById("args-filter").value.trim();
    if (args) params.push("args=" + encodeURIComponent(args));
    var result = document.getElementById("result-filter").value.trim();
    if (result) params.push("result=" + encodeURIComponent(result));
    var error = document.getElementById("error-filter").value.trim();
    if (error) params.push("error=" + encodeURIComponent(error));
    var url = "/api/v1/tasks" + (params.length ? "?" + params.join("&") : "");
    fetch(url, {{ method: "DELETE" }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
            alert("Deleted " + data.deleted + " tasks");
            if (data.deleted > 0) {{
                taskOffset = 20;
                if (ws && ws.readyState === WebSocket.OPEN) {{
                    ws.send(JSON.stringify({{}}));
                }}
            }}
        }})
        .catch(function(err) {{ alert("Delete failed: " + err); }});
}}
function loadMore() {{
    var limit = taskOffset + 20;
    taskOffset = limit;
    var taskName = document.getElementById("task-name-filter").value.trim();
    var url = "/api/v1/tasks?limit=" + limit;
    if (taskName) url += "&task_name=" + encodeURIComponent(taskName);
    fetch(url)
        .then(function(r) {{ return r.json(); }})
        .then(function(tasks) {{
            var table = document.getElementById("tasks-table");
            if (tasks.length === 0) {{
                table.innerHTML = '<div class="empty">No more tasks</div>';
                return;
            }}
            var html = '<table><thead><tr><th>ID</th><th>Task</th><th>Queue</th>'
                + '<th>Args</th><th>Result</th><th>Error</th><th>Status</th><th>TTL</th>'
                + '<th>Actions</th></tr></thead><tbody>';
            function esc(s) {{ return s.replace(/\x22/g,'&quot;'); }}
            var isAdmin = currentUser && currentUser.role === "admin";
            for (var i = 0; i < tasks.length; i++) {{
                var t = tasks[i];
                var tid = (t.id || "").substr(0,8);
                var status = t.status || "unknown";
                var validStates = ["pending","running","completed","failed","cancelled"];
                var badge = "badge-" + (validStates.indexOf(status) >= 0 ? status : "pending");
                var argsStr = t.args ? t.args.join(", ") : "";
                if (t.kwargs) {{
                    for (var k in t.kwargs) {{
                        argsStr += (argsStr ? ", " : "") + k + "=" + t.kwargs[k];
                    }}
                }}
                var resultVal = t.result || "";
                var errorVal = t.error || "";
                var ttl = t.ttl_remaining || "";
                html += '<tr><td class="mono">' + tid + '...</td>';
                html += '<td class="name">' + (t.task_name || "") + '</td>';
                html += '<td>' + (t.queue_name || "") + '</td>';
                html += '<td class="trunc" title="' + esc(argsStr) + '">' + argsStr.substr(0,60) + '</td>';
                html += '<td class="trunc" title="' + esc(resultVal) + '">' + resultVal.substr(0,60) + '</td>';
                html += '<td class="trunc err" title="' + esc(errorVal) + '">' + errorVal.substr(0,60) + '</td>';
                html += '<td><span class="badge ' + badge + '">' + status + '</span></td>';
                html += '<td class="mono">' + ttl + '</td>';
                if (isAdmin) {{
                    if (status === "pending") {{
                        html += '<td class="actions"><button class="btn-action danger"'
                            + ' onclick="confirmAction(' + "'" + t.id + "'" + ',' + "'cancel'" + ')">Cancel</button></td>';
                    }} else if (status === "failed") {{
                        html += '<td class="actions"><button class="btn-action"'
                            + ' onclick="confirmAction(' + "'" + t.id + "'" + ',' + "'requeue'" + ')">Requeue</button></td>';
                    }} else {{
                        html += '<td class="actions"></td>';
                    }}
                }} else {{
                    html += '<td class="actions"></td>';
                }}
                html += '</tr>';
            }}
            html += '</tbody></table>';
            if (tasks.length < limit) {{
                html += '<div class="empty">All tasks loaded</div>';
                document.getElementById("load-more").style.display = "none";
            }}
            table.innerHTML = html;
        }});
}}
function showChangePassword() {{
    document.getElementById("change-pw-error").textContent = "";
    document.getElementById("cp-current").value = "";
    document.getElementById("cp-new").value = "";
    document.getElementById("change-pw-modal").classList.add("open");
}}
function closeChangePassword() {{
    document.getElementById("change-pw-modal").classList.remove("open");
}}
function doChangePassword() {{
    var current = document.getElementById("cp-current").value;
    var newPw = document.getElementById("cp-new").value;
    if (!current || !newPw) {{
        document.getElementById("change-pw-error").textContent = "Both fields are required";
        return;
    }}
    fetch("/account/password", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{current_password:current,new_password:newPw}})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
        if (data.error) {{
            document.getElementById("change-pw-error").textContent = data.error;
        }} else {{
            alert("Password changed successfully");
            closeChangePassword();
        }}
    }})
    .catch(function(err) {{ document.getElementById("change-pw-error").textContent = "Request failed"; }});
}}
connect();
</script>
</body>
</html>""",
        media_type="text/html",
    )


def admin_users_page(users: list[dict[str, Any]], queues: list[str]) -> HTMLResponse:
    rows = ""
    for u in users:
        perms = u.get("permissions", {}) or {}
        queue_perms = perms.get("queues", {}) if isinstance(perms, dict) else {}
        perm_text = json_module.dumps(queue_perms) if queue_perms else "none"
        rows += f"""
        <tr>
            <td>{u["username"]}</td>
            <td><span class="role-badge role-{u['role']}">{u['role']}</span></td>
            <td style="font-size:0.75rem;color:#9ca3af;max-width:200px;overflow:hidden;text-overflow:ellipsis">{perm_text}</td>
            <td>{u.get("created_at", "")[:10]}</td>
            <td>
                <button class="btn-sm" onclick="changeRole('{u['id']}','{u['role']}')">Role</button>
                <button class="btn-sm" onclick="editPerms('{u['id']}',{json_module.dumps(queue_perms)})">Perms</button>
                <button class="btn-sm danger" onclick="deleteUser('{u['id']}','{u['username']}')">Delete</button>
            </td>
        </tr>"""
    queue_options = "".join(f"<option value='{q}'>{q}</option>" for q in queues)

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Manage Users - Lapinq</title>
<style>{CSS}</style>
</head>
<body>
<div class="admin-wrap">
  <h1>Manage Users <a href="/">&larr; Dashboard</a></h1>

  <div class="create-form">
    <div><label>Username</label><input id="new-username" type="text"></div>
    <div><label>Password</label><input id="new-password" type="password"></div>
    <div><label>Role</label>
      <select id="new-role">
        <option value="user">User</option>
        <option value="admin">Admin</option>
      </select></div>
    <button class="btn-sm primary" onclick="createUser()">Create User</button>
  </div>

  <table>
    <thead><tr><th>Username</th><th>Role</th><th>Permissions</th><th>Created</th><th>Actions</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>

<div class="modal-overlay" id="role-modal">
  <div class="modal-box">
    <h2>Change Role</h2>
    <label for="role-select">New Role</label>
    <select id="role-select"><option value="user">User</option><option value="admin">Admin</option></select>
    <div class="actions">
      <button onclick="closeModal('role-modal')">Cancel</button>
      <button class="primary" id="role-save-btn">Save</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="perms-modal">
  <div class="modal-box">
    <h2>Edit Permissions</h2>
    <p style="font-size:0.8125rem;color:#6b7280;margin-bottom:1rem">Allow user to delete/cancel tasks in specific queues. Leave empty = no access.</p>
    <div id="perms-list"></div>
    <div class="actions">
      <button onclick="closeModal('perms-modal')">Cancel</button>
      <button class="primary" id="perms-save-btn">Save</button>
    </div>
  </div>
</div>

<script>
let editingUserId = null;
let editingPerms = {{}};

function createUser() {{
    var username = document.getElementById("new-username").value.trim();
    var password = document.getElementById("new-password").value;
    var role = document.getElementById("new-role").value;
    if (!username || !password) return alert("Username and password required");
    fetch("/admin/users", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{username:username,password:password,role:role}})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
        if (data.error) return alert("Error: " + data.error);
        location.reload();
    }})
    .catch(function(err) {{ alert("Failed: " + err); }});
}}
function changeRole(userId, currentRole) {{
    editingUserId = userId;
    document.getElementById("role-select").value = currentRole;
    document.getElementById("role-save-btn").onclick = function() {{
        var newRole = document.getElementById("role-select").value;
        fetch("/admin/users/" + userId + "/role", {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{role:newRole}})
        }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
            if (data.error) return alert("Error: " + data.error);
            location.reload();
        }})
        .catch(function(err) {{ alert("Failed: " + err); }});
    }};
    document.getElementById("role-modal").classList.add("open");
}}
function editPerms(userId, perms) {{
    editingUserId = userId;
    editingPerms = perms || {{}};
    var list = document.getElementById("perms-list");
    list.innerHTML = "";
    var queues = {json_module.dumps(queues)};
    for (var i = 0; i < queues.length; i++) {{
        var q = queues[i];
        var qPerms = editingPerms[q] || [];
        var div = document.createElement("div");
        div.style.cssText = "margin-bottom:0.5rem;display:flex;align-items:center;gap:0.5rem";
        div.innerHTML = '<span style="font-size:0.8125rem;min-width:100px">' + q + '</span>'
            + '<label><input type="checkbox" value="delete" ' + (qPerms.indexOf("delete") >= 0 ? "checked" : "") + '> delete</label>'
            + '<label><input type="checkbox" value="cancel" ' + (qPerms.indexOf("cancel") >= 0 ? "checked" : "") + '> cancel</label>';
        list.appendChild(div);
    }}
    document.getElementById("perms-save-btn").onclick = function() {{
        var result = {{}};
        var items = list.querySelectorAll("div");
        for (var j = 0; j < items.length; j++) {{
            var qName = items[j].querySelector("span").textContent;
            var checks = items[j].querySelectorAll("input:checked");
            var permsList = [];
            for (var k = 0; k < checks.length; k++) {{
                permsList.push(checks[k].value);
            }}
            if (permsList.length > 0) result[qName] = permsList;
        }}
        fetch("/admin/users/" + editingUserId + "/permissions", {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{queues:result}})
        }})
        .then(function(r) {{ return r.json(); }})
        .then(function(data) {{
            if (data.error) return alert("Error: " + data.error);
            location.reload();
        }})
        .catch(function(err) {{ alert("Failed: " + err); }});
    }};
    document.getElementById("perms-modal").classList.add("open");
}}
function deleteUser(userId, username) {{
    if (!confirm("Delete user '" + username + "'?")) return;
    fetch("/admin/users/" + userId, {{method:"DELETE"}})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
        if (data.error) return alert("Error: " + data.error);
        location.reload();
    }})
    .catch(function(err) {{ alert("Failed: " + err); }});
}}
function closeModal(id) {{
    document.getElementById(id).classList.remove("open");
}}
</script>
</body>
</html>""")


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
                <span class="c-cancelled"><span class="num">{q["cancelled"]}</span> cancelled</span>
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
        valid_statuses = ("pending", "running", "completed", "failed", "cancelled")
        badge = f"badge-{status}" if status in valid_statuses else "badge-pending"

        args_str = _args_str(t)
        result_val = t.get("result")
        error_val = t.get("error")
        ttl = t.get("ttl_remaining", "")

        action_buttons = ""
        if status == "pending":
            action_buttons = (
                f'<button class="btn-action danger"'
                f' onclick="confirmAction(\'{t["id"]}\',\'cancel\')">Cancel</button>'
            )
        elif status == "failed":
            action_buttons = (
                f'<button class="btn-action"'
                f' onclick="confirmAction(\'{t["id"]}\',\'requeue\')">Requeue</button>'
            )

        rows += f"""
        <tr>
            <td class="mono">{tid}...</td>
            <td class="name">{t.get("task_name", "")}</td>
            <td>{t.get("queue_name", "")}</td>
            <td class="trunc" title="{args_str}">{_fmt(args_str)}</td>
            <td class="trunc" title="{result_val or ""}">{_fmt(result_val)}</td>
            <td class="trunc err" title="{error_val or ""}">{_fmt(error_val)}</td>
            <td><span class="badge {badge}">{status}</span></td>
            <td class="mono">{ttl}</td>
            <td class="actions">{action_buttons}</td>
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
                <th>TTL</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>"""
