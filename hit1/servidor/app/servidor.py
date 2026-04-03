from docker.api import image
from fastapi import FastAPI, responses
from pydantic import BaseModel
from typing import Any, Container, Dict
from docker.models.containers import Container
from docker.errors import APIError, ImageNotFound
import requests
import docker
import time
import socket

app = FastAPI()

TAREAS = ["ocurrencias_palabras",
          ]
cliente = docker.from_env()


class Tarea(BaseModel):
    imagen: str
    tarea: str
    parametros: Dict[str, Any]
    datos: Dict[str, Any]


class Resultado(BaseModel):
    estado: str
    datos: Dict[str, Any] | None = None


class Fallo(BaseModel):
    estado: str
    mensaje: str



@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/tareas_soportadas")
def devolver_tareas():
    return{"tareas_soportadas": TAREAS}


@app.post("/getRemoteTask")
def ejecutar_tarea_remota(tarea: Tarea) -> Resultado | Fallo:
    print("ENTRO AL ENDPOINT", flush=True)
    if (tarea.tarea not in TAREAS):
        return Fallo(estado="error",
                     mensaje="La tarea no está soportada",
                     )
    print("tarea existe")

    try:
        pull_imagen(tarea.imagen, False)
    except ImageNotFound:
        return Fallo(estado="error",
                     mensaje="La imagen no se pudo encontrar",
                     )
    except APIError as e:
        # print(f"error al hacer pull: {e}")
        return Fallo(estado="error",
                     mensaje="Problema al hacer pull de la imagen",
                     )
    print("imagen pulleada")

    contenedor = levantar_worker(tarea.imagen)
    print("worker levantado")
    try:
        contenedor.reload()
        # puerto = int(contenedor.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]) # type: ignore
        puerto = 5000
        url_base: str = f"http://localhost:{puerto}"
        print(f"puerto: {puerto}")

        if not esperar_worker(f"{url_base}/health"):
            return Fallo(estado="error",
                         mensaje="Worker no disponible",
                         )
        print("worker activo")

        datos_resultado: Dict[str, Any] = ejecutar(url_base, tarea)
        print(f"resultados: {datos_resultado}")
        return Resultado(estado="ok",
                         datos=datos_resultado,
                         )
    except RuntimeError as e:
        return Fallo(estado="error",
                     mensaje=str(e),
                     )
    finally:
        destruir_worker(contenedor)


def levantar_worker(imagen: str) -> Container:
    contenedor: Container = cliente.containers.run(
            imagen,
            detach=False,
            ports={"5000/tcp": 5000},
            )
    return contenedor


def esperar_worker(url: str, reintentos: int = 10, delay: float = 0.5) -> bool:
    for _ in range(reintentos):
        try:
            requests.get(url)
            return True
        except requests.RequestException:
            time.sleep(delay)
    return False


def ejecutar(url_base: str, tarea: Tarea) -> Dict[str, Any]:
    respuesta: requests.Response
    if tarea.tarea == "ocurrencias_palabras":
        if not tarea.datos["texto"]:
            raise RuntimeError("No se encontro texto a contar")
        respuesta = requests.get(f"{url_base}/contar_palabras", {"cuerpo_texto": tarea.datos["texto"]})
    else:
        raise RuntimeError("Tarea no reconocida")
    respuesta.raise_for_status()
    return respuesta.json()


def destruir_worker(c: Container) -> None:
    c.stop() # type: ignore
    c.remove() # type: ignore


def pull_imagen(imagen: str, check_existe: bool = True) -> None:
    if check_existe:
        try:
            cliente.images.get(imagen)
        except ImageNotFound:
            cliente.images.pull(imagen)
    else:
        cliente.images.pull(imagen)


# def obtener_puerto_libre(): -> int:
    # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
