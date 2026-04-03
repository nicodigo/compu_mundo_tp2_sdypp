from fastapi import FastAPI, responses
from pydantic import BaseModel
from typing import Any, Container, Dict
from docker.models.containers import Container
import requests
import docker
import time

app = FastAPI()

TAREAS = ["ocurrencias_palabras",
          ]
cliente = docker.from_env()


class Tarea(BaseModel):
    imagen: str
    tarea: str
    parametros: dict[str, Any]
    datos: dict[str, Any]



@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/tareas_soportadas")
def devolver_tareas():
    return{"tareas_soportadas": TAREAS}


@app.get("/getRemoteTask")
def ejecutar_tarea_remota(tarea: Tarea):
    if (tarea.tarea not in TAREAS):
        return {"resultado": {
            "estado": "error",
            "valor": "la tarea no está soportada",
            },
                }

    contenedor = levantar_worker(tarea.imagen)
    try:
        puerto = int(contenedor.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]) # type: ignore
        url_base: str = f"http://localhost:{puerto}"
        if not esperar_worker(f"{url_base}/health"):
            raise RuntimeError("Worker no disponible")
        resultado: Dict[str, Any] = ejecutar(url_base, tarea)
        return resultado
    except RuntimeError as e:
        print(e)
    finally:
        destruir_worker(contenedor)


def levantar_worker(imagen: str) -> Container:
    contenedor: Container = cliente.containers.run(
            imagen,
            detach=True,
            ports={"5000/tcp": None},
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
    if tarea == "ocurrencias_palabras":
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
