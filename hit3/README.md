# Hit #3 — Coordinación y Tolerancia a Fallos

## Descripción general

Extensión del Hit #1. Se despliegan tres instancias del servidor detrás de un balanceador de carga Nginx. Las instancias coordinan entre sí mediante el algoritmo Bully para elegir un líder. El líder no cumple un rol diferente al resto en el procesamiento de tareas — el balanceo lo realiza Nginx — pero es el nodo de referencia para el estado del sistema y el punto de detección de fallos.

---

## Arquitectura

```
Cliente HTTP
     │
     │  POST /getRemoteTask (JSON)
     ▼
┌──────────────┐
│    Nginx     │  :8080 → :80  (round-robin)
└──────┬───────┘
       │
  ┌────┼────┐
  ▼    ▼    ▼
 [S1] [S2] [S3]   ← servidores FastAPI :8000
       │
       │  (cada servidor puede levantar un worker)
       ▼
  [worker_temp]   ← contenedor efímero Docker :5000
```

Todos los servicios comparten la red Docker `red_servidores`. Cada servidor tiene acceso al socket del daemon Docker del host para levantar y destruir contenedores worker.

---

## Estructura del proyecto

```
hit3/
├── servidor/
│   ├── app/
│   │   └── servidor.py
│   ├── Dockerfile
│   └── requisitos.txt
├── worker/
│   ├── app/
│   │   └── worker.py
│   ├── Dockerfile
│   └── requisitos.txt
├── docker-compose.yaml
└── nginx.conf
```

---

## Componentes

### Nginx

Balanceador de carga que distribuye las solicitudes entrantes entre los tres servidores usando la estrategia **round-robin** (comportamiento por defecto de Nginx). No tiene conocimiento del estado de liderazgo — trata a los tres nodos como equivalentes.

### Servidor (`servidor.py`)

FastAPI con la misma lógica de ejecución de tareas del Hit #1, extendida con:

- Estado de liderazgo por proceso (`estado: Estado`).
- Algoritmo Bully para elección de líder.
- Monitor de líder en hilo de fondo.
- Endpoints de coordinación entre nodos.

#### Variables de entorno

| Variable   | Descripción                                              | Ejemplo                                   |
|------------|----------------------------------------------------------|-------------------------------------------|
| `NODE_ID`  | Identificador numérico único del nodo                    | `1`                                       |
| `MI_URL`   | URL interna del propio nodo dentro de la red Docker      | `http://servidor1:8000`                   |
| `MI_RED`   | Red Docker donde se levantarán los workers               | `red_servidores`                          |
| `PEERS`    | URLs de los otros nodos, separadas por coma             | `http://servidor2:8000,http://servidor3:8000` |

#### Endpoints

| Método | Endpoint             | Descripción                                                    |
|--------|----------------------|----------------------------------------------------------------|
| GET    | `/`                  | Health check básico                                            |
| GET    | `/tareas_soportadas` | Lista las tareas disponibles                                   |
| GET    | `/health`            | Estado del nodo: ID, lider actual, si hay elección en curso   |
| POST   | `/election`          | Recibe mensaje de elección de otro nodo (protocolo Bully)      |
| POST   | `/coordinator`       | Recibe anuncio del nuevo líder                                 |
| POST   | `/getRemoteTask`     | Ejecuta una tarea remota                                       |

### Worker (`worker.py`)

Idéntico al Hit #1. Contenedor efímero levantado por cualquier servidor que reciba la tarea.

---

## Algoritmo Bully — Elección de líder

El algoritmo Bully elige como líder al nodo con el mayor `NODE_ID` activo. El proceso de elección se dispara cuando:

- El sistema arranca y ningún nodo conoce al líder.
- Un nodo detecta que el líder no responde al `/health` periódico.

### Flujo de elección

1. El nodo que detecta la ausencia del líder llama a `iniciar_eleccion()`.
2. Envía un `POST /election` a todos los nodos con `NODE_ID` mayor al propio.
3. Si ningún nodo responde: el nodo se declara líder y notifica a todos los peers con `POST /coordinator`.
4. Si algún nodo responde con `ok: True`: ese nodo inicia su propia elección. El nodo original espera 7 segundos y si no hay líder nuevo, reintenta.
5. Al recibir `POST /coordinator`: el nodo actualiza su estado local con el nuevo líder.

### Diagrama de secuencia — Caída del líder y nueva elección

Escenario: S3 es el líder (NODE_ID=3). S3 cae. S2 lo detecta primero.

```
S1 (id=1)          S2 (id=2)          S3 (id=3, CAÍDO)
    │                   │                   ✗
    │    monitorear_lider() detecta timeout  │
    │               [2s poll]                │
    │                   │──GET /health──────>✗  (timeout)
    │                   │
    │                   │ iniciar_eleccion()
    │                   │
    │<──POST /election───│  (id=2)
    │   {"id_peer": 2}   │
    │                   │──POST /election──>✗   (S3 caído, sin respuesta)
    │                   │
    │ NODE_ID(1) < 2     │
    │ → responde ok:False│
    │                   │
    │ NODE_ID(1) < 2     │  ningún peer mayor respondió ok:True
    │ inicia elección    │
    │ propia             │  → S2 se declara líder
    │                   │
    │ iniciar_eleccion() │ declarar_lider()
    │──POST /election──>│  (id=1, ninguno mayor activo)
    │   ninguno responde │
    │ → S1 se declara    │──POST /coordinator──>S1
    │   lider también    │  {"id_peer": 2, "url": "..."}
    │                   │
    │<──POST /coordinator│
    │  (lider_id=2)      │
    │  actualiza estado  │
    │                   │
[lider=2]           [lider=2]
```

> En la implementación, S1 también puede iniciar su propia elección en paralelo si `NODE_ID(1) < id_peer(2)` y el nodo no responde `ok:True` sino `ok:False`. El resultado converge al mismo líder porque S2 tiene el mayor ID activo.

---

## Tiempo de recuperación

El tiempo entre la caída del líder y el establecimiento del nuevo está determinado por:

| Etapa                                              | Tiempo aproximado  |
|----------------------------------------------------|--------------------|
| Detección por timeout de `/health`                 | ≤ 2 s (poll cada 2 s + timeout de 2 s) |
| Envío de mensajes `/election` a peers (timeout=1s) | ≤ 1 s por peer     |
| Espera a respuesta de nodos mayores                | ≤ 7 s (timer de verificación) |
| Propagación de `/coordinator` a todos los peers    | < 1 s              |
| **Total en el peor caso**                          | **~12 s**          |
| **Total en el caso típico** (sin peers mayores activos) | **~4–5 s**    |

---

## Redistribución de tareas pendientes

### Comportamiento actual

El balanceador de carga (Nginx) distribuye cada request de forma independiente. Cuando un nodo cae:

- Las tareas **ya en ejecución** en ese nodo se pierden. El cliente recibe un error de conexión o timeout.
- Las tareas **nuevas** son dirigidas por Nginx a los nodos restantes. Nginx detecta la caída del nodo mediante sus propios mecanismos de health check pasivos (conexión rechazada o timeout) y lo excluye automáticamente del pool.
- No existe una cola de tareas pendientes ni mecanismo de reintento automático en el servidor.

### Por qué esta arquitectura no requiere redistribución activa por el líder

La consigna plantea que el coordinador asigne tareas a los workers. En esta implementación, ese rol lo cumple Nginx: el líder no es un dispatcher, sino un nodo de referencia para el estado del sistema. Esta decisión de diseño simplifica la implementación y delega la distribución a una capa probada y eficiente.

### Limitación conocida

Una tarea en vuelo sobre el nodo líder al momento de su caída **no se reintenta**. Para implementar tolerancia a fallos a nivel de tarea sería necesario introducir una cola de mensajes (RabbitMQ, Redis Streams) o un patrón de confirmación explícita por parte del cliente.

---

## Despliegue

### Prerrequisitos

- Docker y Docker Compose instalados en el host.
- `docker login` ejecutado en el host (para pull de imágenes privadas).
- Imagen del worker publicada en Docker Hub.

### Iniciar el sistema completo

```bash
docker compose up -d
```

Esto levanta: Nginx en el puerto `8080`, tres instancias del servidor, y crea la red `red_servidores`.

### Verificar estado de los nodos

```bash
curl http://localhost:8080/health
```

La respuesta incluye el `lider_id` y `lider_url` del nodo que atiende el request.

### Ejecutar una tarea

```bash
curl -X POST http://localhost:8080/getRemoteTask \
  -H "Content-Type: application/json" \
  -d '{
    "imagen": "<usuario>/worker_hit3:v1",
    "tarea": "ocurrencias_palabras",
    "parametros": {},
    "datos": {
      "cuerpo_texto": "el gato y el perro y el gato"
    }
  }'
```

### Simular caída del líder

```bash
# Identificar qué nodo es el líder
curl http://localhost:8080/health

# Matar el contenedor líder (ejemplo: servidor3)
docker stop hit3-servidor3-1

# Observar la nueva elección (~4–12 segundos)
watch -n1 'curl -s http://localhost:8080/health'
```

### Restaurar el nodo caído

```bash
docker start hit3-servidor3-1
```

El nodo se reintegra al pool de Nginx y detecta al líder actual vía el monitor periódico.

---

## Notas

- El nombre fijo `worker_temp` implica que cada nodo solo puede ejecutar una tarea a la vez. Dos requests concurrentes dirigidos al mismo nodo por el balanceador producirán un error en el segundo al intentar crear el contenedor.
- El monitoreo del líder inicia con un delay de 5 segundos al arranque para dar tiempo a que el sistema converja antes de la primera elección.
- `estado.en_eleccion` actúa como mutex lógico para evitar elecciones concurrentes en el mismo nodo, protegido por `threading.Lock`.
