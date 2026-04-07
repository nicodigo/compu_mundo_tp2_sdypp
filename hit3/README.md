# Proyecto: Ejecución de Tareas Remotas con Docker

Arquitectura cliente-servidor donde un servidor FastAPI recibe tareas por HTTP, levanta un contenedor worker Docker para ejecutarlas y devuelve el resultado.

```
proyecto/
├── servidor/
│   ├── app/
│   │   └── servidor.py
│   ├── Dockerfile
│   └── requisitos.txt
└── worker/
    ├── app/
    │   └── worker.py
    ├── Dockerfile
    └── requisitos.txt
```

## Requisitos

- Docker Engine
- Las imágenes del servidor y del worker deben estar construidas o disponibles en Docker Hub

## Puesta en marcha

**1. Crear la red compartida**

```bash
docker network create mi_red
```

Esta red permite que el servidor resuelva el hostname del worker por DNS interno.

**2. Construir las imágenes**

```bash
docker build -t servidor_hit1:v1 ./servidor
docker build -t worker_hit1:v1 ./worker
```

O usar una imagen de worker ya publicada en Docker Hub.

**3. Levantar el servidor**

```bash
docker run \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --network mi_red \
  --name servidor \
  -p 8080:8000 \
  servidor_hit1:v1
```

El socket `/var/run/docker.sock` permite al servidor levantar workers como contenedores hermanos en el daemon del host.

## Flujo de una petición

1. El cliente envía `POST /getRemoteTask` al servidor con imagen, tarea y datos.
2. El servidor hace pull de la imagen del worker si no existe localmente.
3. Levanta el worker como contenedor en `mi_red` con el nombre `worker_temp`.
4. Espera a que el worker responda en `/health`.
5. Envía la tarea al worker y devuelve el resultado.
6. Detiene y elimina el worker.

## Tareas soportadas

| Tarea | Descripción |
|---|---|
| `ocurrencias_palabras` | Cuenta la frecuencia de cada palabra en un texto |

## Ejemplo de petición

```bash
curl -X POST http://127.0.0.1:8080/getRemoteTask \
  -H "Content-Type: application/json" \
  -d '{
    "imagen": "nicodigo/worker_hit1:1.0.1",
    "tarea": "ocurrencias_palabras",
    "parametros": {},
    "datos": {
      "cuerpo_texto": "un texto para probar"
    }
  }'
```

## Notas

- El nombre `worker_temp` está fijo en el servidor. Solo puede ejecutarse una tarea a la vez.
- Si el worker no levanta en 5 segundos (10 reintentos × 0.5s), la tarea falla con `"Worker no disponible"`.
