# Hit #2 — Concurrencia y Exclusión Mutua

## Descripción general

Extensión del Hit #1. El servidor acepta múltiples tareas concurrentes mediante un pool de workers con límite configurable. Las tareas que exceden la capacidad del pool se encolan. Cada tarea recibe un timestamp de Lamport para ordenamiento consistente. Cada worker levanta su propio contenedor Docker independiente, permitiendo ejecución paralela real.

---

## Arquitectura

```
Cliente HTTP (N requests simultáneos)
     │
     │  POST /getRemoteTask (JSON)
     ▼
┌─────────────────────────────────────┐
│  Servidor (FastAPI)  :8000          │
│                                     │
│  ┌──────────────────────────────┐   │
│  │  Cola de tareas (Queue)      │   │
│  │  máx. 50 entradas            │   │
│  └──────────────┬───────────────┘   │
│                 │                   │
│  ┌──────────────▼───────────────┐   │
│  │  Pool de worker_loops        │   │
│  │  N hilos (MAX_WORKERS)       │   │
│  │  Semáforo de N permisos      │   │
│  └──────────────┬───────────────┘   │
└─────────────────┼───────────────────┘
                  │  docker run (por tarea)
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   [worker1]  [worker2]  [workerN]    ← contenedores efímeros :5000
   red: mi_red
```

---

## Estructura del proyecto

```
hit2/
├── servidor/
│   ├── app/
│   │   └── servidor.py
│   └── Dockerfile
├── worker/
│   ├── app/
│   │   └── worker.py
│   ├── Dockerfile
│   └── requisitos.txt
└── ejecutar_n_curls.sh
```

---

## Componentes

### Servidor (`servidor.py`)

FastAPI que implementa el pipeline completo de recepción, encolado y ejecución concurrente de tareas.

#### Endpoints

| Método | Endpoint             | Descripción                        |
|--------|----------------------|------------------------------------|
| GET    | `/`                  | Health check básico                |
| GET    | `/tareas_soportadas` | Lista las tareas disponibles       |
| POST   | `/getRemoteTask`     | Recibe y encola una tarea remota   |

#### Modelo de request (`TareaRemota`)

```json
{
  "imagen": "usuario/worker_hit2:v1",
  "tarea": "ocurrencias_palabras",
  "parametros": {},
  "datos": {
    "cuerpo_texto": "texto a analizar"
  }
}
```

#### Modelo de respuesta exitosa (`Resultado`)

```json
{
  "estado": "ok",
  "datos": {
    "ocurrencias": { "hola": 2, "mundo": 1 }
  }
}
```

#### Modelo de respuesta de error (`Fallo`)

```json
{
  "estado": "error",
  "mensaje": "descripción del error"
}
```

---

## Mecanismos de concurrencia

### Pool de workers

Al iniciar el servidor se lanzan `MAX_WORKERS` hilos daemon, cada uno ejecutando `worker_loop()`. Cada hilo consume tareas de la cola, adquiere un permiso del semáforo, ejecuta la tarea y libera el permiso.

```
worker_loop() [hilo]
    └── cola_tareas.get()          ← bloquea hasta que haya tarea
    └── semaforo_workers.acquire() ← bloquea si no hay permiso libre
    └── ejecutar_tarea_remota()    ← levanta contenedor, ejecuta, destruye
    └── semaforo_workers.release()
    └── cola_tareas.task_done()
```

El número de workers se configura con la variable de entorno `MAX_WORKERS` (por defecto: `4`).

### Cola con exclusión mutua

Se usa `queue.Queue(maxsize=50)` de la biblioteca estándar de Python. `Queue` es thread-safe internamente — utiliza `threading.Lock` y `threading.Condition` para garantizar exclusión mutua en todas las operaciones de enqueue/dequeue. No hay condiciones de carrera al asignar tareas a workers.

Si la cola está llena al momento de encolar una nueva tarea (`put(block=False)`), el servidor retorna inmediatamente un `Fallo` con el mensaje `"Cola de tareas llena"`.

### Sincronización cliente-servidor por tarea

Cada tarea interna contiene un `threading.Event`. El hilo que atiende el request HTTP hace `evento.wait(timeout=30)`. El `worker_loop` hace `evento.set()` al completar o agotar reintentos. Esto permite que el cliente HTTP quede bloqueado eficientemente hasta que su tarea específica termine, sin polling.

### Reintentos

Si la ejecución de una tarea falla, el `worker_loop` la reencola hasta `REINTENTOS_MAX_TAREA` veces (valor por defecto: `2`). Si se agotan los reintentos o la cola está llena al reintentar, se señala el evento con estado `"error"`.

---

## Relojes de Lamport

Cada tarea recibe un timestamp lógico generado por `get_lamport()` en el momento de ser encolada. El reloj es un entero monotónico global protegido por `threading.Lock`.

```python
def get_lamport():
    global clock
    with clock_lock:
        clock += 1
        return clock
```

El timestamp garantiza un ordenamiento total y consistente de las solicitudes recibidas, independientemente del orden de llegada de los hilos. Actualmente el timestamp es **interno**: se asigna a la tarea pero no se expone en la respuesta al cliente.

**Mejora futura:** retornar el `tarea_id` y el `timestamp` en el response permitiría al cliente correlacionar solicitudes y al servidor exponer el orden lógico de procesamiento.

---

## Identificación de contenedores worker

A diferencia del Hit #1, cada contenedor worker recibe un nombre único basado en el `tarea_id`:

```
worker{tarea_id}   →   worker1, worker2, worker3, ...
```

Esto permite ejecución paralela real: múltiples contenedores coexisten simultáneamente en la red `mi_red`, cada uno atendiendo una tarea distinta.

---

## Despliegue

### Prerrequisitos

- Docker instalado en el host.
- Red Docker `mi_red` creada.
- Imagen del worker publicada en Docker Hub.
- `docker login` ejecutado en el host.

### Crear la red Docker

```bash
docker network create mi_red
```

### Iniciar el servidor
** En el directorio del servidor **
```bash
docker compose up
```

El servidor queda disponible en `http://localhost:8080`.

### Ejecutar múltiples tareas concurrentes

El script `ejecutar_n_curls.sh` lanza 150 requests en paralelo:

```bash
chmod +x ejecutar_n_curls.sh
./ejecutar_n_curls.sh
```

---

## Medición de throughput

> **Esta sección debe completarse con los resultados experimentales.**

### Metodología

Se ejecuta `ejecutar_n_curls.sh` (150 requests en paralelo) para cada valor de `MAX_WORKERS`. Se mide el tiempo total desde el primer request hasta la última respuesta y se calcula:

```
Throughput = tareas_completadas / tiempo_total_minutos
```

### Recursos compartidos como cuellos de botella

Dado que todo corre en un único host, los recursos compartidos entre contenedores son:

| Recurso | Motivo de contención | Cómo medirlo |
|---|---|---|
| **Daemon de Docker** | Todas las operaciones `docker run`, `docker stop`, `docker rm` pasan por un único daemon serializado | `time docker run ...` bajo carga; latencia del socket `/var/run/docker.sock` |
| **CPU** | Cada contenedor worker ejecuta procesamiento de texto; múltiples workers compiten por los mismos núcleos | `docker stats` o `htop` durante la prueba |
| **Memoria RAM** | Cada contenedor FastAPI consume memoria base (~50 MB); con N=8 el consumo base es significativo | `docker stats --no-stream` |
| **Red Docker (`mi_red`)** | El servidor se comunica con cada worker vía HTTP interno; bajo alta concurrencia hay contención en el bridge | `iftop` o `nethogs` en la interfaz `docker0` |
| **I/O de disco** | El pull de imágenes y los logs de cada contenedor generan escrituras; relevante en la primera ejecución | `iostat -x 1` durante la prueba |

El cuello de botella más probable con esta arquitectura es el **daemon de Docker**: serializa la creación y destrucción de contenedores, por lo que el speedup deja de ser lineal antes de saturar CPU o red.

---

## Notas

- El timeout de espera por tarea es de 30 segundos. Si el worker no responde en ese tiempo, el cliente recibe un error de timeout.
- La cola admite hasta 50 tareas pendientes. Requests que lleguen con la cola llena son rechazados inmediatamente.
- El semáforo limita la ejecución simultánea a `MAX_WORKERS` tareas, pero los hilos `worker_loop` siguen vivos y consumiendo de la cola indefinidamente.
