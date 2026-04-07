# Hit #1 — Servidor de Tareas Remotas con Workers Docker

## Descripción general

Sistema distribuido compuesto por un servidor HTTP y un servicio de tarea ("worker"), ambos contenerizados. El servidor recibe solicitudes de clientes, levanta dinámicamente un contenedor worker para ejecutar la tarea solicitada, obtiene el resultado y destruye el contenedor. La comunicación entre servidor y worker ocurre dentro de una red Docker privada.

---

## Arquitectura

```
Cliente HTTP
     │
     │  POST /getRemoteTask (JSON)
     ▼
┌─────────────┐        Docker daemon (socket montado)
│  Servidor   │───────────────────────────────────────┐
│  (FastAPI)  │                                       │
│  :8000      │  1. pull imagen                       │
└─────────────┘  2. docker run (worker_temp)          │
     │           3. esperar /health                   │
     │           4. PUT /contar_palabras              ▼
     │         ┌──────────────────────────────────────┐
     │         │  Worker (FastAPI)  :5000              │
     │         │  red: mi_red / nombre: worker_temp   │
     │         └──────────────────────────────────────┘
     │           5. resultado JSON
     │           6. stop + remove contenedor
     │
     ▼
Respuesta al cliente
```

---

## Estructura del proyecto

```
hit1
├── servidor
│   ├── app
│   │    └── servidor.py
│   ├── Dockerfile
│   └── requisitos.txt
├── worker
│   ├── app
│   │    └── worker.py
│   ├── Dockerfile
│   └── requisitos.txt
```

---

## Componentes

### Servidor (`servidor.py`)

Servidor FastAPI que expone los siguientes endpoints:

| Método | Endpoint            | Descripción                                      |
|--------|---------------------|--------------------------------------------------|
| GET    | `/`                 | Health check básico                              |
| GET    | `/tareas_soportadas`| Lista las tareas disponibles                     |
| POST   | `/getRemoteTask`    | Punto de entrada principal — ejecuta una tarea   |

#### Modelo de request (`Tarea`)

```json
{
  "imagen": "nombre/imagen:tag",
  "tarea": "ocurrencias_palabras",
  "parametros": {},
  "datos": {
    "cuerpo_texto": "texto a analizar"
  }
}
```

- `imagen`: imagen Docker que contiene el worker a usar.
- `tarea`: nombre de la tarea a ejecutar. Debe estar en la lista `TAREAS`.
- `parametros`: campo reservado para parámetros adicionales de tareas futuras.
- `datos`: datos de entrada específicos para la tarea.

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

#### Flujo interno de `ejecutarTareaRemota()`

1. Valida que la tarea esté en `TAREAS`.
2. Hace `pull` de la imagen Docker indicada.
3. Levanta el worker como contenedor en la red `mi_red` con nombre `worker_temp`.
4. Espera hasta 5 segundos (10 reintentos × 0.5 s) a que el worker responda en `/health`.
5. Delega la ejecución al worker vía HTTP.
6. Retorna el resultado al cliente.
7. En el bloque `finally`: detiene y elimina el contenedor, independientemente del resultado.

---

### Worker (`worker.py`)

Servicio FastAPI liviano, efímero, que implementa la tarea concreta.

| Método | Endpoint          | Descripción                        |
|--------|-------------------|------------------------------------|
| GET    | `/`               | Health check básico                |
| GET    | `/health`         | Usado por el servidor para esperar disponibilidad |
| PUT    | `/contar_palabras`| Cuenta ocurrencias de palabras     |

#### Tarea implementada: `ocurrencias_palabras`

Recibe un texto, elimina caracteres no alfabéticos (conservando caracteres con tilde y ñ), convierte a minúsculas y retorna un conteo de ocurrencias por palabra.

**Request:**

```json
{
  "cuerpo_texto": "Hola mundo hola"
}
```

**Response:**

```json
{
  "ocurrencias": {
    "hola": 2,
    "mundo": 1
  }
}
```

---

## Dependencias

```
fastapi[standard]
docker
requests
```

---

## Despliegue

### Prerrequisitos

- Docker instalado en el host.
- La imagen del worker publicada en Docker Hub (o registry accesible desde el host).
- Autenticación Docker configurada en el host (ver sección de Seguridad).

### 1. Crear la red Docker

```bash
docker network create mi_red
```

Esta red debe existir antes de iniciar el servidor. Es la red interna por la que servidor y worker se comunican. El worker es alcanzado por su nombre de contenedor (`worker_temp`) como hostname dentro de esta red.

### 2. Hacer un pull de la imagen del servidor

```bash
docker pull nicodigo/servidor_hit1:1.0
```

### 3. Iniciar el servidor

```bash
docker run \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --name servidor \
  -p 8080:8000 \
  --network mi_red \
  servidor_hit1:1.0
```

El servidor queda disponible en `http://localhost:8080`.

La opción `-v /var/run/docker.sock:/var/run/docker.sock` monta el socket del daemon Docker del host dentro del contenedor del servidor, permitiéndole levantar y destruir contenedores worker directamente sobre el host.

---

## Uso

### Verificar tareas soportadas

```bash
curl http://localhost:8080/tareas_soportadas
```

### Ejecutar tarea `ocurrencias_palabras`

```bash
curl -X POST http://localhost:8080/getRemoteTask \
  -H "Content-Type: application/json" \
  -d '{
    "imagen": "<usuario>/worker_hit1:v1",
    "tarea": "ocurrencias_palabras",
    "parametros": {},
    "datos": {
      "cuerpo_texto": "el gato y el perro y el gato"
    }
  }'
```

También se puede utilizar la interfaz interactiva en `http://localhost:8080/docs`.

---

## Seguridad — Autenticación al registro Docker

### Problema

La consigna prohíbe enviar credenciales del registry Docker en el payload del request. Enviarlas en el JSON implicaría que cualquier cliente del servidor podría leerlas, y que viajarían en texto plano por la red (o en logs HTTP).

### Solución implementada: configuración previa en el host con `docker login`

El servidor accede al daemon Docker a través del socket montado (`/var/run/docker.sock`). Esto significa que **las operaciones Docker del servidor se ejecutan como el daemon del host**, con sus credenciales ya configuradas.

Al ejecutar en el host:

```bash
docker login
```

Las credenciales quedan almacenadas en `~/.docker/config.json` del host. Cuando el servidor hace `pull` de una imagen, el daemon del host utiliza esas credenciales almacenadas — el servidor nunca las ve, nunca las manipula y nunca las transmite.

### Por qué es más seguro que enviar usuario y contraseña en el JSON

| Criterio                        | `docker login` en el host     | Credenciales en el JSON       |
|---------------------------------|-------------------------------|-------------------------------|
| Exposición en tránsito          | Ninguna                       | Viajan en cada request        |
| Visibilidad para el cliente     | Nula                          | El cliente las posee          |
| Aparición en logs HTTP          | No                            | Sí, si se loguea el body      |
| Rotación de credenciales        | Solo en el host               | Requiere actualizar el cliente|
| Superficie de ataque            | Limitada al host              | Ampliada a cada cliente       |

### Alternativas de mayor seguridad para entornos productivos

- **Token de acceso de corta duración**: Docker Hub y registries compatibles permiten generar tokens con expiración y permisos acotados (solo lectura). Se configura igual que `docker login` pero con menor superficie de compromiso.
- **OIDC Federation**: El host se autentica ante el registry usando identidad federada (ej. rol de IAM en AWS ECR), sin credenciales estáticas.
- **Image Pull Secrets** (en Kubernetes): las credenciales se almacenan como Secret cifrado en el cluster y son inyectadas por el orquestador, nunca expuestas al cliente.

---

## Extensibilidad

El campo `parametros` del modelo `Tarea` y la estructura de `ejecutar()` están diseñados para incorporar nuevas tareas sin cambiar el contrato del endpoint. Para agregar una tarea:

1. Agregar el nombre a la lista `TAREAS` en `servidor.py`.
2. Agregar el caso correspondiente en la función `ejecutar()`.
3. Implementar el endpoint en el worker (o en un worker nuevo con su propia imagen).
4. Construir y publicar la nueva imagen Docker del worker.

---

## Notas

- El contenedor worker siempre es destruido al finalizar la tarea, incluso si ocurre un error (bloque `finally`).
- El nombre fijo `worker_temp` implica que el servidor no soporta ejecución concurrente de tareas. Si dos requests llegan simultáneamente, el segundo falla al intentar crear un contenedor con el mismo nombre.
- El servidor expone el puerto `8000` internamente; se mapea al `8080` del host en el ejemplo de despliegue.
