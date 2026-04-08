# Servidor

FastAPI que expone una API HTTP para ejecutar tareas delegadas a workers Docker.

## Estructura

```
servidor/
├── app/
│   └── servidor.py
├── Dockerfile
└── requisitos.txt
```

## Endpoints

### `GET /`
Healthcheck básico.

### `GET /tareas_soportadas`
Devuelve la lista de tareas que el servidor puede delegar.

```json
{
  "tareas_soportadas": ["ocurrencias_palabras"]
}
```

### `POST /getRemoteTask`
Ejecuta una tarea en un worker Docker.

**Body:**
```json
{
  "imagen": "string",
  "tarea": "string",
  "parametros": {},
  "datos": {}
}
```

**Respuesta exitosa:**
```json
{
  "estado": "ok",
  "datos": {}
}
```

**Respuesta de error:**
```json
{
  "estado": "error",
  "mensaje": "string"
}
```

**Errores posibles:**

| Mensaje | Causa |
|---|---|
| `La tarea no está soportada` | `tarea` no figura en `TAREAS` |
| `La imagen no se pudo encontrar` | La imagen no existe en Docker Hub |
| `Problema al hacer pull de la imagen` | Error de daemon al hacer pull |
| `Worker no disponible` | El worker no respondió en `/health` dentro del tiempo límite |
| `No se encontro texto a contar` | El campo `cuerpo_texto` está ausente o vacío en `datos` |

## Construcción

```bash
docker build -t servidor_hit1:v1 .
```

## Ejecución

Requiere la red `mi_red` creada previamente (`docker network create mi_red`).

```bash
docker run \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --network mi_red \
  --name servidor \
  -p 8080:8000 \
  nicodigo/servidor_hit1:v1
```

## Dependencias relevantes

- `fastapi` + `uvicorn`: servidor HTTP
- `docker`: cliente Python para controlar el daemon del host vía socket montado
- `requests`: comunicación HTTP con el worker
- `pydantic`: validación de modelos de entrada y salida
