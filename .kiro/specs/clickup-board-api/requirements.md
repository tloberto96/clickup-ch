# Requirements Document

## Introduction

ClickUp Board API es una API serverless construida en Python puro (sin dependencias externas) que se ejecuta sobre AWS Lambda + API Gateway. Expone endpoints REST para consultar workspaces, espacios, tableros y tareas de ClickUp, agregar comentarios y exportar datos a CSV. Complementa la API un frontend estático (HTML/JS/CSS) deployado en S3 + CloudFront que permite a los usuarios interactuar con el tablero desde el browser sin necesidad de herramientas adicionales.

La autenticación se delega completamente a ClickUp: el usuario provee su API Key personal mediante el header `X-ClickUp-Token` y ClickUp valida los permisos en cada request.

---

## Glossary

- **API**: La Lambda Function expuesta a través de API Gateway que implementa los endpoints REST.
- **Lambda_Handler**: El entrypoint `main.handler` de AWS Lambda que recibe eventos de API Gateway y despacha al router.
- **Router**: El componente interno que mapea método HTTP + path a un handler específico.
- **ClickUp_API**: La API externa de ClickUp (`https://api.clickup.com/api/v2`) a la que la Lambda realiza requests en nombre del usuario.
- **Token**: La API Key personal del usuario de ClickUp, transmitida en el header `X-ClickUp-Token`.
- **Workspace**: Un equipo (team) en ClickUp, identificado por `team_id`.
- **Space**: Un espacio dentro de un Workspace, identificado por `space_id`.
- **List**: Un tablero (lista de tareas) dentro de un Space o Folder, identificado por `list_id`.
- **Task**: Una tarea dentro de un List, identificada por `task_id`.
- **Custom_Field**: Un campo personalizado definido en un List de ClickUp, aplanado como columna `cf_<nombre>` en el CSV.
- **CSV_Exporter**: El componente que convierte tareas a formato CSV con UTF-8 BOM.
- **Frontend**: La aplicación web estática (`frontend/index.html`) deployada en S3 + CloudFront.
- **CloudFront_Origin**: La URL de la distribución CloudFront desde la que el browser realiza requests a la API.
- **CORS**: Política de Cross-Origin Resource Sharing configurada en la API para permitir requests desde el CloudFront_Origin.

---

## Requirements

### Requirement 1: Autenticación mediante API Key de ClickUp

**User Story:** Como usuario de ClickUp, quiero autenticarme con mi API Key personal, para que la API acceda a mis recursos de ClickUp con mis propios permisos.

#### Acceptance Criteria

1. THE Lambda_Handler SHALL extraer el valor del header `X-ClickUp-Token` de cada request entrante de forma case-insensitive.
2. IF el header `X-ClickUp-Token` está ausente, contiene un valor vacío o contiene únicamente caracteres de espacio en blanco, THEN THE Lambda_Handler SHALL retornar HTTP 401 con un body JSON `{"detail": "Header X-ClickUp-Token requerido."}`.
3. WHEN la ClickUp_API retorna un error 401 o 403 para un Token dado, THE Lambda_Handler SHALL propagar ese código de estado HTTP y el cuerpo de la respuesta de ClickUp al cliente sin modificarlos.
4. THE Lambda_Handler SHALL incluir el Token como valor directo (sin prefijo `Bearer`) en el header `Authorization` de todas las requests a la ClickUp_API.

---

### Requirement 2: Health Check

**User Story:** Como operador del sistema, quiero un endpoint de health check, para que pueda verificar que la Lambda está operativa sin necesidad de autenticación.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request `GET /health`, THE Lambda_Handler SHALL retornar HTTP 200 con `Content-Type: application/json` y el body `{"status": "ok"}`.
2. IF la request es `GET /health`, THEN THE Lambda_Handler SHALL procesar la request sin verificar la presencia del header `X-ClickUp-Token`, omitiendo la validación de autenticación definida en el Requirement 1.

---

### Requirement 3: Listado de Workspaces

**User Story:** Como usuario de ClickUp, quiero listar los workspaces accesibles con mi token, para que pueda identificar el `team_id` necesario para consultas posteriores.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /workspaces`, THE Lambda_Handler SHALL retornar HTTP 200 con un body JSON que contenga la clave `workspaces` con un array de objetos, uno por cada workspace accesible para el Token provisto.
2. THE Lambda_Handler SHALL incluir en cada objeto del array los campos: `id` (string), `name` (string), `color` (string o null), `avatar` (string o null) y `members_count` (entero derivado del tamaño del array `members` en la respuesta de ClickUp).
3. IF el array de workspaces está vacío, THEN THE Lambda_Handler SHALL retornar HTTP 200 con `{"workspaces": []}`.
4. IF la ClickUp_API retorna un error HTTP al consultar workspaces, THEN THE Lambda_Handler SHALL retornar el mismo código de estado HTTP con un body JSON `{"detail": <cuerpo de la respuesta de ClickUp>}`.

---

### Requirement 4: Listado de Spaces de un Workspace

**User Story:** Como usuario de ClickUp, quiero listar los espacios de un workspace, para que pueda identificar el `space_id` necesario para consultar sus tableros.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /workspaces/{team_id}/spaces`, THE Lambda_Handler SHALL enviar a la ClickUp_API el parámetro `archived=false` y retornar HTTP 200 con un body JSON que contenga la clave `spaces` con un array de los espacios no archivados del workspace identificado por `team_id`.
2. THE Lambda_Handler SHALL incluir en cada space los campos: `id`, `name`, `private`, `archived` y `statuses`.
3. IF el `team_id` no existe o el Token no tiene acceso, THEN THE Lambda_Handler SHALL retornar el código de error que provea la ClickUp_API con un mensaje descriptivo.

---

### Requirement 5: Listado de Lists (Tableros) de un Space

**User Story:** Como usuario de ClickUp, quiero listar todos los tableros de un espacio, para que pueda identificar el `list_id` del tablero que quiero consultar.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /spaces/{space_id}/lists`, THE Lambda_Handler SHALL retornar HTTP 200 con la lista de Lists del space identificado por `space_id`.
2. IF el query parameter `include_folders` está ausente o tiene el valor `true`, THEN THE Lambda_Handler SHALL incluir en la respuesta tanto las Lists directas del space como las Lists contenidas en Folders del mismo space.
3. IF el query parameter `include_folders` tiene el valor `false`, THEN THE Lambda_Handler SHALL retornar únicamente las Lists directas del space, sin realizar requests a la ClickUp_API para obtener Folders.
4. THE Lambda_Handler SHALL incluir en cada List los campos: `id`, `name`, `task_count`, `folder` (null si no pertenece a un folder, o un objeto `{id, name}` si pertenece) y `archived`.
5. IF el `space_id` no existe o el Token no tiene acceso, THEN THE Lambda_Handler SHALL retornar el código de error que provea la ClickUp_API con un mensaje descriptivo.
6. IF la ClickUp_API falla al consultar los Folders del space, THEN THE Lambda_Handler SHALL retornar el código de error correspondiente con un mensaje descriptivo.

---

### Requirement 6: Consulta Completa de un Tablero

**User Story:** Como usuario de ClickUp, quiero obtener todos los datos de un tablero en una sola request, para que pueda visualizar tareas, miembros, vistas y campos personalizados sin múltiples llamadas.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /board/{list_id}`, THE Lambda_Handler SHALL retornar HTTP 200 con un body JSON que contenga las claves: `list`, `tasks_count`, `tasks`, `members`, `views` y `custom_fields`.
2. THE Lambda_Handler SHALL paginar automáticamente las requests a la ClickUp_API para obtener todas las Tasks del List, solicitando 100 tareas por página hasta que una página retorne menos de 100 tareas.
3. THE Lambda_Handler SHALL incluir subtareas y tareas cerradas en el resultado de paginación enviando los parámetros `subtasks=true` e `include_closed=true` a la ClickUp_API.
4. IF el query parameter `include_members` está ausente o tiene el valor `true`, THEN THE Lambda_Handler SHALL incluir la lista de miembros con acceso al List en la clave `members`.
5. IF el query parameter `include_views` está ausente o tiene el valor `true`, THEN THE Lambda_Handler SHALL incluir las vistas configuradas en el List en la clave `views`.
6. IF el query parameter `include_custom_fields` está ausente o tiene el valor `true`, THEN THE Lambda_Handler SHALL incluir la definición de los Custom_Fields del List en la clave `custom_fields`.
7. IF la consulta de miembros, vistas o custom fields falla, THEN THE Lambda_Handler SHALL retornar igualmente HTTP 200 con los datos disponibles, dejando la clave correspondiente como array vacío `[]`.
8. IF el `list_id` no existe o el Token no tiene acceso, THEN THE Lambda_Handler SHALL retornar HTTP 401, 403 o 404 según corresponda a la respuesta de la ClickUp_API.

---

### Requirement 7: Detalle de una Tarea

**User Story:** Como usuario de ClickUp, quiero obtener el detalle completo de una tarea específica, para que pueda ver todos sus campos, subtareas y custom fields.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /board/{list_id}/tasks/{task_id}`, THE Lambda_Handler SHALL retornar HTTP 200 con todos los campos de la Task tal como los provee la ClickUp_API, incluyendo subtareas (parámetro `include_subtasks=true`) y Custom_Fields.
2. IF el `task_id` no existe o el Token no tiene acceso, THEN THE Lambda_Handler SHALL retornar el código de error que provea la ClickUp_API.

---

### Requirement 8: Gestión de Comentarios de una Tarea

**User Story:** Como usuario de ClickUp, quiero leer y agregar comentarios en tareas, para que pueda colaborar con mi equipo directamente desde la interfaz.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /board/{list_id}/tasks/{task_id}/comments`, THE Lambda_Handler SHALL retornar HTTP 200 con un body JSON `{"comments": [...]}` con la lista de comentarios de la Task.
2. WHEN THE Lambda_Handler recibe una request autenticada `POST /board/{list_id}/tasks/{task_id}/comments` con un body JSON válido, THE Lambda_Handler SHALL publicar el comentario en la ClickUp_API y retornar HTTP 201 con la respuesta de ClickUp.
3. IF el body del `POST /comments` no contiene el campo `comment_text`, contiene un valor vacío, contiene únicamente caracteres de espacio en blanco, o supera los 10.000 caracteres, THEN THE Lambda_Handler SHALL retornar HTTP 422 con un body JSON `{"detail": "El campo comment_text es requerido."}` sin realizar ninguna request a la ClickUp_API.
4. IF el body del `POST /comments` no es JSON válido, THEN THE Lambda_Handler SHALL retornar HTTP 400 con un body JSON `{"detail": "Body JSON inválido."}`.
5. IF el campo `notify_all` está ausente o es `false`, THEN THE Lambda_Handler SHALL enviar `notify_all: false` a la ClickUp_API.
6. WHERE el campo `notify_all` del body sea `true`, THE Lambda_Handler SHALL incluir `notify_all: true` en la request a la ClickUp_API.
7. IF la ClickUp_API retorna un error al leer o publicar comentarios, THEN THE Lambda_Handler SHALL propagar el código de estado y el cuerpo del error al cliente.

---

### Requirement 9: Exportación CSV del Tablero

**User Story:** Como usuario de ClickUp, quiero exportar todas las tareas de un tablero a CSV, para que pueda analizar los datos en Excel u otras herramientas.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /board/{list_id}/export/csv`, THE Lambda_Handler SHALL obtener todas las Tasks del List con paginación automática y retornar HTTP 200 con el archivo CSV.
2. THE CSV_Exporter SHALL incluir el último comentario de cada Task en la columna `last_comment`. IF una Task no tiene comentarios o la request de comentarios falla, THEN la columna `last_comment` SHALL contener una cadena vacía.
3. THE CSV_Exporter SHALL generar el CSV con exactamente las columnas en este orden: `name`, `status`, `assignees`, `last_comment` y `PM`. La columna `assignees` SHALL contener los usernames separados por coma. La columna `PM` SHALL contener el valor del Custom_Field `cf_Asignee`.
4. THE CSV_Exporter SHALL codificar el CSV en UTF-8 con BOM (byte order mark `\xef\xbb\xbf`).
5. WHEN THE Lambda_Handler retorna el CSV, THE Lambda_Handler SHALL codificarlo en base64, incluir el header `Content-Type: text/csv`, el header `Content-Disposition: attachment; filename="<nombre>.csv"` y el campo `isBase64Encoded: true` en la respuesta de Lambda.
6. WHEN THE Lambda_Handler genera el nombre del archivo, THE Lambda_Handler SHALL usar el formato `clickup_<list_name>_<YYYYMMDDTHHmmss>UTC.csv`, donde `list_name` es el nombre del List con espacios reemplazados por guiones bajos. IF la request al nombre del List falla, THEN SHALL usar el `list_id` como `list_name`.
7. IF el `list_id` no existe o el Token no tiene acceso, THEN THE Lambda_Handler SHALL retornar el código de error correspondiente de la ClickUp_API.

---

### Requirement 10: Exportación CSV de una Tarea Individual

**User Story:** Como usuario de ClickUp, quiero exportar el detalle de una tarea específica a CSV, para que pueda compartir o archivar la información de esa tarea.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request autenticada `GET /board/{list_id}/tasks/{task_id}/export/csv`, THE Lambda_Handler SHALL retornar HTTP 200 con un archivo CSV de una sola fila de datos que contenga el detalle de la Task, con el header `Content-Disposition: attachment; filename="clickup_task_<task_id>_<timestamp>.csv"`.
2. IF el query parameter `include_comments` tiene el valor `true`, THEN THE CSV_Exporter SHALL agregar una columna `comments` con el historial completo de comentarios de la tarea, con el formato `[YYYY-MM-DD HH:MM:SS UTC] usuario: texto` por cada comentario, separados por ` | `.
3. IF el query parameter `filtered` tiene el valor `true`, THEN THE CSV_Exporter SHALL excluir del CSV las columnas: `priority`, `creator`, `date_created`, `date_closed`, `start_date`, `time_estimate_ms`, `points`, `parent`, `list`, `folder`, `space_id` y `cf_Situación Actual`.
4. THE CSV_Exporter SHALL aplanar cada Custom_Field de la tarea como una columna `cf_<nombre>` en el CSV. IF el valor del Custom_Field es null o está ausente, THEN la celda SHALL contener una cadena vacía.
5. THE CSV_Exporter SHALL codificar el CSV en UTF-8 con BOM.
6. IF el `task_id` no existe o el Token no tiene acceso, THEN THE Lambda_Handler SHALL retornar el código de error que provea la ClickUp_API.

---

### Requirement 11: CORS y Compatibilidad con API Gateway

**User Story:** Como operador del sistema, quiero que la API maneje correctamente CORS y sea compatible con ambas versiones de API Gateway, para que el frontend pueda consumirla desde CloudFront sin errores de browser.

#### Acceptance Criteria

1. WHEN THE Lambda_Handler recibe una request con método `OPTIONS`, THE Lambda_Handler SHALL retornar HTTP 204 con los headers: `Access-Control-Allow-Origin: <CloudFront_Origin>`, `Access-Control-Allow-Headers: Content-Type,X-ClickUp-Token`, `Access-Control-Allow-Methods: GET,POST,OPTIONS` y `Access-Control-Max-Age: 300`, sin requerir autenticación.
2. THE Lambda_Handler SHALL incluir en todas las respuestas (incluyendo errores) los headers: `Access-Control-Allow-Origin` con el valor exacto del CloudFront_Origin configurado, `Access-Control-Allow-Headers: Content-Type,X-ClickUp-Token` y `Access-Control-Allow-Methods: GET,POST,OPTIONS`.
3. WHEN THE Lambda_Handler recibe un evento de API Gateway HTTP API (payload format 2.0), THE Lambda_Handler SHALL extraer el método HTTP de `requestContext.http.method` y el path de `rawPath`.
4. WHEN THE Lambda_Handler recibe un evento de API Gateway REST API (payload format 1.0), THE Lambda_Handler SHALL extraer el método HTTP de `httpMethod` y el path de `path`.
5. IF el path recibido termina en `/` y no es exactamente `/`, THEN THE Lambda_Handler SHALL eliminar el trailing slash antes de enrutar la request.
6. IF el método HTTP y el path no coinciden con ningún endpoint definido, THEN THE Lambda_Handler SHALL retornar HTTP 404 con un body JSON `{"detail": "Endpoint no encontrado: <METHOD> <path>"}`.

---

### Requirement 12: Manejo de Errores Internos

**User Story:** Como operador del sistema, quiero que los errores internos sean capturados y retornados de forma controlada, para que los clientes reciban respuestas JSON consistentes en lugar de errores no manejados.

#### Acceptance Criteria

1. IF ocurre una excepción Python no controlada (distinta de ApiError) dentro del Lambda_Handler, THEN THE Lambda_Handler SHALL retornar HTTP 500 con un body JSON `{"detail": "Error interno: <mensaje de la excepción>"}`.
2. IF la ClickUp_API retorna un error HTTP (instancia de ApiError), THEN THE Lambda_Handler SHALL retornar el mismo código de estado HTTP con un body JSON `{"detail": <cuerpo de la respuesta de ClickUp como string>}`.
3. THE Lambda_Handler SHALL incluir los headers CORS definidos en el Requirement 11 en todas las respuestas de error, incluyendo HTTP 400, 401, 403, 404, 422 y 500.

---

### Requirement 13: Frontend — Visualización del Tablero

**User Story:** Como usuario de ClickUp, quiero una interfaz web para visualizar el tablero, para que pueda ver el estado de las tareas sin usar herramientas de línea de comandos.

#### Acceptance Criteria

1. WHEN el Frontend carga en el browser, THE Frontend SHALL renderizar un campo `<input type="password">` con el atributo `autocomplete="current-password"` para la API Key de ClickUp.
2. WHEN el usuario hace click en "Cargar tablero", THE Frontend SHALL realizar una request `GET /board/{list_id}` a la API. IF la API retorna un error, THEN THE Frontend SHALL mostrar el mensaje de error y no renderizar la tabla de tareas.
3. WHEN el tablero carga exitosamente, THE Frontend SHALL mostrar por cada tarea las columnas: nombre (con link a ClickUp), estado (badge con el color provisto por la API), asignados, tags (pills con el color provisto por la API), último comentario y botón "+ Comentar".
4. WHEN el tablero se carga, THE Frontend SHALL iniciar la carga de comentarios en paralelo para todas las tareas, mostrando un spinner por fila mientras cada request está pendiente.
5. WHEN la request de comentarios de una tarea completa exitosamente, THE Frontend SHALL actualizar la celda con el último comentario truncado visualmente por desbordamiento de contenedor (CSS `text-overflow: ellipsis`) y un tooltip con el texto completo al hacer hover. IF la request falla o la tarea no tiene comentarios, THEN THE Frontend SHALL mostrar `—` en la celda.
6. WHEN el usuario modifica el campo de API Key, THE Frontend SHALL actualizar el badge del header: verde si el campo contiene texto, rojo si está vacío.

---

### Requirement 14: Frontend — Agregar Comentarios

**User Story:** Como usuario de ClickUp, quiero agregar comentarios a tareas desde la interfaz web, para que pueda colaborar con mi equipo sin salir de la herramienta.

#### Acceptance Criteria

1. WHEN el usuario hace click en el botón "+ Comentar" de una tarea, THE Frontend SHALL abrir un modal con un campo de texto para el comentario y un checkbox "Notificar a todos los miembros de la tarea".
2. WHEN el usuario hace click en "Enviar comentario", THE Frontend SHALL deshabilitar el botón de envío y realizar una request `POST /board/{list_id}/tasks/{task_id}/comments` con `comment_text` y `notify_all`. El botón SHALL permanecer deshabilitado hasta recibir la respuesta.
3. IF el campo de comentario está vacío o contiene únicamente espacios en blanco al intentar enviar, THEN THE Frontend SHALL mostrar un mensaje de error indicando que el comentario no puede estar vacío y no SHALL realizar la request a la API.
4. WHEN el comentario se publica exitosamente, THE Frontend SHALL mostrar un mensaje de confirmación visible durante al menos 1.2 segundos y luego cerrar el modal automáticamente.
5. WHEN el usuario presiona la tecla Escape o hace click directamente sobre el overlay del modal (fuera del contenido), THE Frontend SHALL cerrar el modal sin enviar el comentario.
6. IF la API retorna un error al publicar el comentario, THEN THE Frontend SHALL mantener el modal abierto, preservar el texto del comentario, re-habilitar el botón de envío y mostrar el mensaje de error de la API.

---

### Requirement 15: Frontend — Exportación CSV

**User Story:** Como usuario de ClickUp, quiero descargar el CSV del tablero desde la interfaz web, para que pueda exportar los datos con un solo click.

#### Acceptance Criteria

1. WHEN el usuario hace click en "Descargar CSV", THE Frontend SHALL realizar una request `GET /board/{list_id}/export/csv` con el header `X-ClickUp-Token` del usuario.
2. WHEN la API retorna el CSV exitosamente, THE Frontend SHALL crear un objeto URL desde el blob de la respuesta, simular un click en un elemento `<a>` con el atributo `download` para iniciar la descarga, y luego revocar el objeto URL.
3. IF la API retorna un error HTTP o la request falla por error de red, THEN THE Frontend SHALL mostrar el mensaje de error en la interfaz y re-habilitar el botón "Descargar CSV".
4. WHILE la request de exportación está en curso, THE Frontend SHALL mostrar un spinner en el botón "Descargar CSV" y mantenerlo deshabilitado. WHEN la request completa (con éxito o error), THE Frontend SHALL restaurar el botón a su estado original.
