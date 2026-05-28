"""
ClickUp Board API — AWS Lambda Handler (sin dependencias externas)
Compatible con API Gateway HTTP API (payload format 2.0) y REST API (1.0).

Autenticación: todos los endpoints requieren el header X-ClickUp-Token
con la API Key personal del usuario de ClickUp.
"""

import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CLICKUP_API_BASE = "https://api.clickup.com/api/v2"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def clickup_request(method: str, path: str, token: str, params: dict = None, body: dict = None) -> dict:
    """Realiza una request a la API de ClickUp y devuelve el JSON de respuesta."""
    url = f"{CLICKUP_API_BASE}{path}"
    if params:
        # Filtra valores None y convierte booleanos a string lowercase
        clean = {k: str(v).lower() if isinstance(v, bool) else str(v)
                 for k, v in params.items() if v is not None}
        url = f"{url}?{urllib.parse.urlencode(clean)}"

    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise ApiError(e.code, error_body)


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


# ---------------------------------------------------------------------------
# ClickUp data helpers
# ---------------------------------------------------------------------------

def get_all_tasks(list_id: str, token: str) -> list:
    all_tasks = []
    page = 0
    while True:
        data = clickup_request("GET", f"/list/{list_id}/task", token,
                               params={"page": page, "subtasks": True, "include_closed": True})
        tasks = data.get("tasks", [])
        all_tasks.extend(tasks)
        if len(tasks) < 100:
            break
        page += 1
    return all_tasks


def get_task_detail(task_id: str, token: str) -> dict:
    return clickup_request("GET", f"/task/{task_id}", token, params={"include_subtasks": True})


def get_task_comments(task_id: str, token: str) -> list:
    data = clickup_request("GET", f"/task/{task_id}/comment", token)
    return data.get("comments", [])


def get_list_members(list_id: str, token: str) -> list:
    return clickup_request("GET", f"/list/{list_id}/member", token).get("members", [])


def get_list_views(list_id: str, token: str) -> list:
    return clickup_request("GET", f"/list/{list_id}/view", token).get("views", [])


def get_list_custom_fields(list_id: str, token: str) -> list:
    return clickup_request("GET", f"/list/{list_id}/field", token).get("fields", [])


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def ms_to_iso(ms_str) -> str:
    if not ms_str:
        return ""
    try:
        return datetime.fromtimestamp(int(ms_str) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        return str(ms_str)


def flatten_task(task: dict) -> dict:
    assignees = ", ".join(a.get("username", a.get("email", "")) for a in task.get("assignees", []))
    tags      = ", ".join(t.get("name", "") for t in task.get("tags", []))
    priority  = (task.get("priority") or {}).get("priority", "")
    status    = (task.get("status") or {}).get("status", "")
    creator   = (task.get("creator") or {}).get("username", "")
    list_name = (task.get("list") or {}).get("name", "")
    folder    = (task.get("folder") or {}).get("name", "")
    space_id  = (task.get("space") or {}).get("id", "")

    comments_text = ""
    for c in task.get("_comments", []):
        user = (c.get("user") or {}).get("username", "?")
        date = ms_to_iso(str(c.get("date", "")))
        text = c.get("comment_text", "")
        if not text:
            blocks = c.get("comment", [])
            text = " ".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("text"))
        text = text.replace("\n", " ").strip()
        if text:
            comments_text += f"[{date}] {user}: {text} | "
    comments_text = comments_text.rstrip(" | ")

    # Último comentario
    last_comment = ""
    raw_comments = task.get("_comments", [])
    if raw_comments:
        c = raw_comments[-1]
        user = (c.get("user") or {}).get("username", "?")
        date = ms_to_iso(str(c.get("date", "")))
        text = c.get("comment_text", "")
        if not text:
            blocks = c.get("comment", [])
            text = " ".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("text"))
        text = text.replace("\n", " ").strip()
        if text:
            last_comment = f"[{date}] {user}: {text}"

    row = {
        "id":             task.get("id", ""),
        "name":           task.get("name", ""),
        "status":         status,
        "priority":       priority,
        "creator":        creator,
        "assignees":      assignees,
        "tags":           tags,
        "description":    (task.get("description") or "").replace("\n", " "),
        "date_created":   ms_to_iso(task.get("date_created")),
        "date_updated":   ms_to_iso(task.get("date_updated")),
        "date_closed":    ms_to_iso(task.get("date_closed")),
        "due_date":       ms_to_iso(task.get("due_date")),
        "start_date":     ms_to_iso(task.get("start_date")),
        "time_estimate_ms": task.get("time_estimate") or "",
        "points":         task.get("points") or "",
        "parent":         task.get("parent") or "",
        "list":           list_name,
        "folder":         folder,
        "space_id":       space_id,
        "url":            task.get("url", ""),
        "comments":       comments_text,
        "last_comment":   last_comment,
    }

    for cf in task.get("custom_fields", []):
        col   = f"cf_{cf.get('name', cf.get('id', ''))}"
        value = cf.get("value")
        if isinstance(value, dict):
            value = value.get("username") or value.get("name") or str(value)
        elif isinstance(value, list):
            value = ", ".join(
                (v.get("label") or v.get("name") or v.get("username") or str(v))
                if isinstance(v, dict) else str(v)
                for v in value
            )
        row[col] = value if value is not None else ""

    return row


DEFAULT_EXCLUDED_COLUMNS = {
    "priority", "creator", "date_created", "date_closed", "start_date",
    "time_estimate_ms", "points", "parent", "list", "folder", "space_id",
    "cf_Situación Actual",
}

# Columnas para el export simplificado del frontend
FRONTEND_COLUMNS = ["name", "status", "assignees", "last_comment", "cf_PM"]


def tasks_to_csv(tasks: list, exclude: set = None) -> str:
    if not tasks:
        return ""
    rows = [flatten_task(t) for t in tasks]
    all_keys, seen = [], set()
    for row in rows:
        for k in row:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    if exclude:
        all_keys = [k for k in all_keys if k not in exclude]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=all_keys, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def tasks_to_csv_frontend(tasks: list) -> str:
    """CSV simplificado: name, status, assignees, last_comment, PM (cf_Asignee)."""
    if not tasks:
        return ""
    rows = [flatten_task(t) for t in tasks]
    display_rows = []
    for r in rows:
        display_rows.append({
            "name":         r.get("name", ""),
            "status":       r.get("status", ""),
            "assignees":    r.get("assignees", ""),
            "last_comment": r.get("last_comment", ""),
            "PM":           r.get("cf_Asignee", ""),
        })
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["name", "status", "assignees", "last_comment", "PM"],
                            extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(display_rows)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Request / Response helpers
# ---------------------------------------------------------------------------

def get_token(event: dict) -> str:
    """Extrae X-ClickUp-Token de los headers (case-insensitive)."""
    headers = event.get("headers") or {}
    # API Gateway puede enviar headers en minúsculas
    normalized = {k.lower(): v for k, v in headers.items()}
    token = normalized.get("x-clickup-token", "").strip()
    if not token:
        raise ApiError(401, "Header X-ClickUp-Token requerido.")
    return token


def get_query(event: dict, key: str, default=None):
    """Extrae un query parameter del evento de API Gateway."""
    params = event.get("queryStringParameters") or {}
    val = params.get(key)
    if val is None:
        return default
    if isinstance(default, bool):
        return val.lower() in ("true", "1", "yes")
    return val


CORS_ORIGIN = "https://dj7m5s65g119j.cloudfront.net"
CORS_HEADERS = {
    "Access-Control-Allow-Origin":  CORS_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,X-ClickUp-Token",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def json_response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **CORS_HEADERS},
        "body": json.dumps(body, ensure_ascii=False),
    }


def csv_response(content: str, filename: str) -> dict:
    import base64
    encoded = base64.b64encode(content.encode("utf-8-sig")).decode()
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/csv",
            "Content-Disposition": f'attachment; filename="{filename}"',
            **CORS_HEADERS,
        },
        "body": encoded,
        "isBase64Encoded": True,
    }


def error_response(err: ApiError) -> dict:
    return json_response(err.status, {"detail": err.detail})


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def route(event: dict) -> dict:
    """Despacha el evento al handler correcto según método y path."""
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path   = event.get("path") or event.get("rawPath") or "/"
    method = method.upper()

    # Normaliza path: elimina trailing slash excepto en "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # OPTIONS — preflight CORS
    if method == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": {
                "Access-Control-Allow-Origin":  "https://dj7m5s65g119j.cloudfront.net",
                "Access-Control-Allow-Headers": "Content-Type,X-ClickUp-Token",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Max-Age":       "300",
            },
            "body": "",
        }

    # GET /health
    if method == "GET" and path == "/health":
        return json_response(200, {"status": "ok"})

    # GET /workspaces
    if method == "GET" and path == "/workspaces":
        return handle_get_workspaces(event)

    # GET /workspaces/{team_id}/spaces
    if method == "GET" and path_match(path, "/workspaces/{}/spaces"):
        team_id = path.split("/")[2]
        return handle_get_spaces(event, team_id)

    # GET /spaces/{space_id}/lists
    if method == "GET" and path_match(path, "/spaces/{}/lists"):
        space_id = path.split("/")[2]
        return handle_get_lists(event, space_id)

    # GET /board/{list_id}
    if method == "GET" and path_match(path, "/board/{}") and len(path.split("/")) == 3:
        list_id = path.split("/")[2]
        return handle_get_board(event, list_id)

    # GET /board/{list_id}/export/csv
    if method == "GET" and path_match(path, "/board/{}/export/csv"):
        list_id = path.split("/")[2]
        return handle_export_board_csv(event, list_id)

    # GET /board/{list_id}/tasks/{task_id}
    if method == "GET" and path_match(path, "/board/{}/tasks/{}") and not path.endswith("/export/csv"):
        parts = path.split("/")
        list_id, task_id = parts[2], parts[4]
        return handle_get_task(event, list_id, task_id)

    # GET /board/{list_id}/tasks/{task_id}/export/csv
    if method == "GET" and path_match(path, "/board/{}/tasks/{}/export/csv"):
        parts = path.split("/")
        list_id, task_id = parts[2], parts[4]
        return handle_export_task_csv(event, list_id, task_id)

    # GET /board/{list_id}/tasks/{task_id}/comments
    if method == "GET" and path_match(path, "/board/{}/tasks/{}/comments"):
        parts = path.split("/")
        list_id, task_id = parts[2], parts[4]
        return handle_get_comments(event, list_id, task_id)

    # POST /board/{list_id}/tasks/{task_id}/comments
    if method == "POST" and path_match(path, "/board/{}/tasks/{}/comments"):
        parts = path.split("/")
        list_id, task_id = parts[2], parts[4]
        return handle_add_comment(event, list_id, task_id)

    return json_response(404, {"detail": f"Endpoint no encontrado: {method} {path}"})


def path_match(path: str, pattern: str) -> bool:
    """Compara un path con un patrón donde {} es un segmento variable."""
    path_parts    = path.strip("/").split("/")
    pattern_parts = pattern.strip("/").split("/")
    if len(path_parts) != len(pattern_parts):
        return False
    return all(pp == "{}" or pp == ap for pp, ap in zip(pattern_parts, path_parts))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_get_workspaces(event: dict) -> dict:
    token = get_token(event)
    data  = clickup_request("GET", "/team", token)
    teams = data.get("teams", [])
    return json_response(200, {
        "workspaces": [
            {"id": t["id"], "name": t["name"], "color": t.get("color"),
             "avatar": t.get("avatar"), "members_count": len(t.get("members", []))}
            for t in teams
        ]
    })


def handle_get_spaces(event: dict, team_id: str) -> dict:
    token  = get_token(event)
    data   = clickup_request("GET", f"/team/{team_id}/space", token, params={"archived": False})
    spaces = data.get("spaces", [])
    return json_response(200, {
        "team_id": team_id,
        "spaces": [
            {"id": s["id"], "name": s["name"], "private": s.get("private", False),
             "archived": s.get("archived", False), "statuses": s.get("statuses", [])}
            for s in spaces
        ],
    })


def handle_get_lists(event: dict, space_id: str) -> dict:
    token           = get_token(event)
    include_folders = get_query(event, "include_folders", True)

    folderless = clickup_request("GET", f"/space/{space_id}/list", token, params={"archived": False})
    lists = [
        {"id": l["id"], "name": l["name"], "task_count": l.get("task_count"),
         "folder": None, "archived": l.get("archived", False)}
        for l in folderless.get("lists", [])
    ]

    if include_folders:
        folders_data = clickup_request("GET", f"/space/{space_id}/folder", token, params={"archived": False})
        for folder in folders_data.get("folders", []):
            for l in folder.get("lists", []):
                lists.append({
                    "id": l["id"], "name": l["name"], "task_count": l.get("task_count"),
                    "folder": {"id": folder["id"], "name": folder["name"]},
                    "archived": l.get("archived", False),
                })

    return json_response(200, {"space_id": space_id, "lists_count": len(lists), "lists": lists})


def handle_get_board(event: dict, list_id: str) -> dict:
    token              = get_token(event)
    include_members    = get_query(event, "include_members", True)
    include_views      = get_query(event, "include_views", True)
    include_cf         = get_query(event, "include_custom_fields", True)
    task_detail_flag   = get_query(event, "task_detail", False)

    list_info = clickup_request("GET", f"/list/{list_id}", token)
    tasks     = get_all_tasks(list_id, token)

    if task_detail_flag:
        tasks = [get_task_detail(t["id"], token) for t in tasks]

    members, views, custom_fields = [], [], []
    if include_members:
        try:
            members = get_list_members(list_id, token)
        except ApiError:
            pass
    if include_views:
        try:
            views = get_list_views(list_id, token)
        except ApiError:
            pass
    if include_cf:
        try:
            custom_fields = get_list_custom_fields(list_id, token)
        except ApiError:
            pass

    return json_response(200, {
        "list": list_info,
        "tasks_count": len(tasks),
        "tasks": tasks,
        "members": members,
        "views": views,
        "custom_fields": custom_fields,
    })


def handle_get_task(event: dict, list_id: str, task_id: str) -> dict:
    token = get_token(event)
    task  = get_task_detail(task_id, token)
    return json_response(200, task)


def handle_get_comments(event: dict, list_id: str, task_id: str) -> dict:
    token    = get_token(event)
    comments = get_task_comments(task_id, token)
    return json_response(200, {"comments": comments})


def handle_add_comment(event: dict, list_id: str, task_id: str) -> dict:
    token = get_token(event)
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return json_response(400, {"detail": "Body JSON inválido."})

    comment_text = body.get("comment_text", "").strip()
    if not comment_text:
        return json_response(422, {"detail": "El campo comment_text es requerido."})

    notify_all = bool(body.get("notify_all", False))
    result = clickup_request("POST", f"/task/{task_id}/comment", token,
                             body={"comment_text": comment_text, "notify_all": notify_all})
    return {**json_response(201, result), "statusCode": 201}


def handle_export_board_csv(event: dict, list_id: str) -> dict:
    token            = get_token(event)

    tasks = get_all_tasks(list_id, token)

    # Siempre incluye el último comentario de cada tarea
    for task in tasks:
        try:
            task["_comments"] = get_task_comments(task["id"], token)
        except ApiError:
            task["_comments"] = []

    list_name = list_id
    try:
        info      = clickup_request("GET", f"/list/{list_id}", token)
        list_name = info.get("name", list_id).replace(" ", "_")
    except ApiError:
        pass

    content  = tasks_to_csv_frontend(tasks)
    filename = f"clickup_{list_name}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return csv_response(content, filename)


def handle_export_task_csv(event: dict, list_id: str, task_id: str) -> dict:
    token            = get_token(event)
    include_comments = get_query(event, "include_comments", False)
    filtered         = get_query(event, "filtered", False)

    task = get_task_detail(task_id, token)
    if include_comments:
        try:
            task["_comments"] = get_task_comments(task_id, token)
        except ApiError:
            task["_comments"] = []

    exclude  = DEFAULT_EXCLUDED_COLUMNS if filtered else None
    content  = tasks_to_csv([task], exclude=exclude)
    filename = f"clickup_task_{task_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return csv_response(content, filename)


# ---------------------------------------------------------------------------
# Lambda entrypoint
# ---------------------------------------------------------------------------

def handler(event, context):
    try:
        return route(event)
    except ApiError as e:
        return error_response(e)
    except Exception as e:
        return json_response(500, {"detail": f"Error interno: {str(e)}"})
