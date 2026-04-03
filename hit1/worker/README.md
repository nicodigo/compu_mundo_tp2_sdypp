# Worker

FastAPI liviano que ejecuta una tarea específica. Es levantado por el servidor como contenedor efímero, atiende una petición y es destruido.

## Estructura

```
worker/
├── app/
│   └── worker.py
├── Dockerfile
└── requisitos.txt
```

## Endpoints

### `GET /health`
Usado por el servidor para confirmar que el worker está listo antes de enviarle trabajo.

```json
{ "status": "ok" }
```

### `PUT /contar_palabras`
Cuenta la frecuencia de cada palabra en el texto recibido.

**Body:**
```json
{
  "cuerpo_texto": "un texto para probar"
}
```

**Respuesta:**
```json
{
  "ocurrencias": {
    "un": 1,
    "texto": 1,
    "para": 1,
    "probar": 1
  }
}
```

El texto es normalizado antes de contar: se eliminan caracteres no alfabéticos (se conservan tildes y ñ) y se convierte a minúsculas.

## Construcción

```bash
docker build -t worker_hit1:v1 .
```

## Ejecución standalone (para pruebas)

```bash
docker run --rm -p 5000:5000 worker_hit1:v1
```

En producción el servidor lo levanta automáticamente en la red `mi_red` con el nombre `worker_temp`.

## Notas

- El worker no tiene estado. Cada instancia atiende una única petición dentro del ciclo de vida gestionado por el servidor.
- El puerto expuesto es `5000`.
