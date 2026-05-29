# ClickUp Board API

API serverless construida en Python puro (sin dependencias externas) que corre sobre **AWS Lambda + API Gateway**. Expone endpoints GET/POST para obtener todos los datos de un tablero de ClickUp y sus tareas, exportar CSVs y agregar comentarios.

---

## Autenticación

Todos los endpoints requieren el header `X-ClickUp-Token` con la **API Key personal** del usuario de ClickUp. ClickUp valida los permisos directamente — si el usuario no tiene acceso al recurso, ClickUp devuelve 401/403.

> **¿Dónde obtengo mi API Key?**
> En ClickUp: `Settings → Apps → API Token → Generate`.

---

## Deploy en AWS Lambda

### 1. Generar el ZIP

```powershell
powershell -ExecutionPolicy Bypass -File .\build_lambda.ps1
```

Genera `lambda_package.zip` (~10 KB). No requiere Docker ni instalación de dependencias.

### 2. Crear la Lambda Function

En AWS Console → Lambda → Create function:

| Campo | Valor |
|---|---|
| Runtime | Python 3.12 |
| Architecture | x86_64 |
| Handler | `main.handler` |
| Timeout | 29 segundos (límite de API Gateway) |

Subir el archivo `lambda_package.zip` generado. No se necesitan variables de entorno.

### 3. Crear API Gateway

La opción recomendada es **HTTP API** (más simple y económica):

1. API Gateway → Create API → **HTTP API**
2. Integration: Lambda Function → seleccioná tu Lambda
3. Route: `ANY /{proxy+}`
4. Deploy → anotá la URL base (ej: `https://abc123.execute-api.us-east-1.amazonaws.com`)

> Si usás **REST API** en lugar de HTTP API, agregá `text/csv` en Settings → Binary Media Types para que la descarga de CSVs funcione correctamente.

---

## URL base

Todos los ejemplos usan `{BASE_URL}` como placeholder. Reemplazalo con tu URL de API Gateway:

```
https://abc123.execute-api.us-east-1.amazonaws.com
```

---

## Endpoints

### `GET /health`

Verifica que la Lambda está corriendo.

```bash
curl {BASE_URL}/health
```

```json
{ "status": "ok" }
```

---

### `GET /workspaces`

Lista todos los workspaces accesibles con el token provisto.

```bash
curl -H "X-ClickUp-Token: pk_tutoken" {BASE_URL}/workspaces
```

```json
{
  "workspaces": [
    { "id": "90171038160", "name": "Mi Empresa", "members_count": 5 }
  ]
}
```

---

### `GET /workspaces/{team_id}/spaces`

Lista todos los espacios de un workspace. Usá el `id` del workspace obtenido en el paso anterior.

```bash
curl -H "X-ClickUp-Token: pk_tutoken" {BASE_URL}/workspaces/90171038160/spaces
```

```json
{
  "team_id": "90171038160",
  "spaces": [
    { "id": "90175395111", "name": "CloudHesive Internal", "private": true }
  ]
}
```

---

### `GET /spaces/{space_id}/lists`

Lista todos los tableros (Lists) de un espacio. El `id` de cada lista es el `list_id` para los endpoints de tablero.

**Query parameters opcionales:**

| Parámetro | Default | Descripción |
|---|---|---|
| `include_folders` | `true` | Incluir listas dentro de carpetas |

```bash
curl -H "X-ClickUp-Token: pk_tutoken" {BASE_URL}/spaces/90175395111/lists
```

```json
{
  "space_id": "90175395111",
  "lists_count": 3,
  "lists": [
    { "id": "901713225426", "name": "Sprint 1", "task_count": 42, "folder": null }
  ]
}
```

---

### `GET /board/{list_id}`

Devuelve todos los datos del tablero: info, tareas, miembros, vistas y campos personalizados.

**Query parameters opcionales:**

| Parámetro | Default | Descripción |
|---|---|---|
| `include_members` | `true` | Incluir miembros con acceso al tablero |
| `include_views` | `true` | Incluir vistas configuradas |
| `include_custom_fields` | `true` | Incluir definición de campos personalizados |
| `task_detail` | `false` | Detalle completo por tarea (una request extra por tarea, más lento) |

```bash
curl -H "X-ClickUp-Token: pk_tutoken" {BASE_URL}/board/901713225426
```

```json
{
  "list": { "id": "901713225426", "name": "Sprint 1", ... },
  "tasks_count": 42,
  "tasks": [ ... ],
  "members": [ ... ],
  "views": [ ... ],
  "custom_fields": [ ... ]
}
```

---

### `GET /board/{list_id}/tasks/{task_id}`

Devuelve el detalle completo de una tarea específica.

```bash
curl -H "X-ClickUp-Token: pk_tutoken" {BASE_URL}/board/901713225426/tasks/abc123xyz
```

---

### `POST /board/{list_id}/tasks/{task_id}/comments`

Agrega un comentario a una tarea. El comentario se publica como el usuario dueño del token.

**Body JSON:**

| Campo | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `comment_text` | string | ✅ | — | Texto del comentario |
| `notify_all` | boolean | ❌ | `false` | Notifica a todos los miembros de la tarea |

```bash
curl -X POST {BASE_URL}/board/901713225426/tasks/abc123xyz/comments \
  -H "X-ClickUp-Token: pk_tutoken" \
  -H "Content-Type: application/json" \
  -d "{\"comment_text\": \"Mi comentario\", \"notify_all\": false}"
```

---

## Endpoints de exportación CSV

### `GET /board/{list_id}/export/csv`

Descarga un CSV con todas las tareas del tablero. Cada fila es una tarea.

**Query parameters opcionales:**

| Parámetro | Default | Descripción |
|---|---|---|
| `task_detail` | `false` | Detalle completo por tarea (más lento) |
| `include_comments` | `false` | Agrega columna `comments` con la actividad de cada tarea (una request extra por tarea) |
| `filtered` | `false` | Excluye columnas no esenciales (ver lista abajo) |

```bash
# Export básico
curl -o tablero.csv -H "X-ClickUp-Token: pk_tutoken" \
  {BASE_URL}/board/901713225426/export/csv

# Con comentarios y columnas filtradas
curl -o tablero.csv -H "X-ClickUp-Token: pk_tutoken" \
  "{BASE_URL}/board/901713225426/export/csv?include_comments=true&filtered=true"
```

**Columnas excluidas con `filtered=true`:**
`priority`, `creator`, `date_created`, `date_closed`, `start_date`, `time_estimate_ms`, `points`, `parent`, `list`, `folder`, `space_id`, `cf_Situación Actual`

**Columnas siempre presentes:**

| Columna | Descripción |
|---|---|
| `id` | ID de la tarea |
| `name` | Nombre |
| `status` | Estado |
| `assignees` | Asignados (separados por coma) |
| `tags` | Etiquetas |
| `description` | Descripción |
| `date_updated` | Última actualización |
| `due_date` | Fecha límite |
| `url` | URL directa en ClickUp |
| `comments` | Actividad (si `include_comments=true`) |
| `cf_<nombre>` | Una columna por cada campo personalizado |

El archivo se descarga en **UTF-8 con BOM** para compatibilidad directa con Excel.

---

### `GET /board/{list_id}/tasks/{task_id}/export/csv`

Descarga un CSV con el detalle de una sola tarea.

**Query parameters opcionales:** `include_comments`, `filtered` (igual que el endpoint anterior).

```bash
curl -o tarea.csv -H "X-ClickUp-Token: pk_tutoken" \
  "{BASE_URL}/board/901713225426/tasks/abc123xyz/export/csv?include_comments=true"
```

---

## ¿Cómo encuentro el `list_id` y `task_id`?

**Desde la API** (recomendado):

```
GET /workspaces                        → obtenés el team_id
GET /workspaces/{team_id}/spaces       → obtenés el space_id
GET /spaces/{space_id}/lists           → obtenés el list_id ✓
GET /board/{list_id}/tasks/{task_id}   → detalle de una tarea
```

**Desde la URL de ClickUp:**

- `list_id`: `https://app.clickup.com/XXXXX/v/l/li/`**`901713225426`**
- `task_id`: `https://app.clickup.com/t/`**`abc123xyz`**

---

## Manejo de errores

| Código | Descripción |
|---|---|
| `401` | Header `X-ClickUp-Token` ausente o API Key inválida |
| `403` | El usuario no tiene acceso al recurso solicitado |
| `404` | El `list_id` o `task_id` no existe |
| `422` | Body inválido (ej: falta `comment_text`) |
| `500` | Error interno de la Lambda |

---

## Estructura del proyecto

```
ch-clickup/
├── main.py                  # Código completo de la API (sin dependencias externas)
├── build_lambda.ps1         # Script para generar lambda_package.zip
├── deploy_frontend.ps1      # Script para subir el frontend a S3 e invalidar CloudFront
├── lambda_package.zip       # ZIP listo para subir a Lambda (generado por el script)
├── requirements.txt         # Sin dependencias (referencia)
├── .env.deploy              # Credenciales AWS para deploy (no se commitea)
├── frontend/
│   └── index.html           # Frontend estático para S3 + CloudFront
└── README.md                # Este archivo
```

---

## Frontend (S3 + CloudFront)

Interfaz web estática (Guri Data Team Board Manager) que permite a los usuarios:
- Ingresar su API Key de ClickUp y cargar el tablero configurado (el formulario se oculta al cargar con éxito y reaparece ante errores)
- Recargar el tablero en cualquier momento con el botón **↺ Recargar** sin necesidad de reingresar el token
- Ver todas las tareas con sus estados, asignados, tags y último comentario
- Filtrar tareas por estado, asignado, tag y actividad reciente (últimas 24 horas) desde un sidebar lateral
- Ordenar la tabla por cualquier columna (nombre, estado, asignados, tags, fecha de comentario)
- Ver el texto completo de un comentario en un popover flotante al hacer click
- Agregar comentarios a tareas individuales
- Descargar el CSV de tareas con dos modalidades:
  - **Con filtro aplicado**: genera el CSV en el cliente con las tareas actualmente visibles (respeta los filtros del sidebar)
  - **Informe completo**: descarga el CSV completo desde la API (método original)
- Cambiar entre modo oscuro y modo claro (preferencia persistida en `localStorage`)
- Usar el **modo demo** con token `testing12345678` para explorar la UI sin una API Key real

### Modo demo

Ingresá `testing12345678` como API Key para activar el modo demo. En este modo:
- Los datos del tablero son ficticios (generados en el cliente)
- Los comentarios no se envían a ClickUp
- Se muestra un banner de aviso en la interfaz

### Deploy en S3 + CloudFront

#### Opción A — Script automatizado (recomendado)

Creá el archivo `.env.deploy` con tus credenciales AWS (nunca se commitea):

```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

Luego ejecutá:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_frontend.ps1
```

El script sube `frontend/index.html` al bucket S3 configurado e invalida la distribución CloudFront automáticamente.

#### Opción B — Manual

**1. Crear el bucket S3**

```bash
aws s3 mb s3://clickup-board-frontend
aws s3 website s3://clickup-board-frontend --index-document index.html
```

**2. Subir el archivo**

```bash
aws s3 cp frontend/index.html s3://clickup-board-frontend/index.html \
  --content-type "text/html" \
  --cache-control "no-cache"
```

**3. Crear distribución CloudFront**

En AWS Console → CloudFront → Create distribution:

| Campo | Valor |
|---|---|
| Origin domain | `clickup-board-frontend.s3-website-<region>.amazonaws.com` |
| Origin protocol | HTTP only |
| Default root object | `index.html` |
| Cache policy | CachingDisabled (para desarrollo) |

**4. Configurar CORS en API Gateway**

Para que el browser pueda llamar a la API desde CloudFront, agregá CORS en API Gateway:

- Allowed origins: `https://tu-distribucion.cloudfront.net`
- Allowed headers: `Content-Type, X-ClickUp-Token`
- Allowed methods: `GET, POST, OPTIONS`

> En HTTP API: API Gateway → tu API → CORS → configurar.
> En REST API: habilitá CORS en cada recurso desde Actions → Enable CORS.

### Uso

1. Abrí la URL de CloudFront en el browser
2. Ingresá tu API Key de ClickUp (`pk_...`) o `testing12345678` para modo demo
3. Hacé click en **Cargar tablero** — el formulario de configuración se oculta automáticamente al cargar con éxito y vuelve a mostrarse si ocurre un error
4. Usá el botón **↺ Recargar** en el encabezado del tablero para refrescar los datos sin tener que reingresar el token
5. Usá el sidebar izquierdo para filtrar por estado, asignado, tag o actividad reciente (últimas 24 horas)
6. Hacé click en cualquier encabezado de columna para ordenar la tabla
7. Hacé click en el texto de un comentario para ver el contenido completo en un popover
8. Hacé click en **+ Comentar** para agregar un comentario a una tarea
9. Usá **↓ Descargar CSV** para exportar las tareas — se abre un modal con dos opciones:
   - **Con filtro aplicado**: exporta solo las tareas visibles (generado en el cliente, instantáneo)
   - **Informe completo**: descarga todas las tareas desde la API
10. Usá el toggle 🌙/☀️ en el header para cambiar entre modo oscuro y claro

---

## Desarrollo local

Para probar localmente sin Lambda podés correr el handler directamente simulando el evento de API Gateway:

```python
# test_local.py
from main import handler

event = {
    "httpMethod": "GET",
    "path": "/health",
    "headers": {},
    "queryStringParameters": {}
}
print(handler(event, None))
```

```bash
python test_local.py
```
