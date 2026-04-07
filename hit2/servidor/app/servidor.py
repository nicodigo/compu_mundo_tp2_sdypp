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
import random

app = FastAPI()

TAREAS = ["ocurrencias_palabras",
          ]
cliente = docker.from_env()

workers = []

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

    pullear_imagen(tarea.imagen)

    contenedor = obtener_worker_nuevo(tarea.imagen)

    if (contenedor == None):
        #enviar tarea a worker activo

        contenedor = obtener_worker()

        try:
            contenedor.reload() # type: ignore

            url_base: str = f"http://{contenedor.name}:5000"

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
    else:
        contenedor = levantar_worker(tarea.imagen)

        print("worker levantado")

        try:
            contenedor.reload() # type: ignore

            url_base: str = f"http://{contenedor.name}:5000"

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
            quitar_worker(contenedor)
            destruir_worker(contenedor)


#Devuelve un worker valido, si hay espacio en workers activos, crea uno, si no, devuelve nulo
def obtener_worker_nuevo(imagen: str) -> Container:

    contenedor = None

    if (len(workers) < 2):
        contenedor = levantar_worker(imagen)
        workers.append(contenedor)
    
    return contenedor


def obtener_worker() -> Container:

    contenedor = workers[random.randint(0 , len(workers) - 1)]

    return contenedor


def levantar_worker(imagen: str) -> Container:

    nombre = "worker_temp"

    if (len(workers) == 0):
        nombre = nombre + "0"
    else:
        nombre = nombre + str(len(workers))

    contenedor: Container = cliente.containers.run(
            imagen,
            detach=True,
            network="mi_red",
            name=nombre,
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
        if not tarea.datos.get("cuerpo_texto"):
            raise RuntimeError("No se encontro texto a contar")
        respuesta = requests.put(f"{url_base}/contar_palabras", json={"cuerpo_texto": tarea.datos["cuerpo_texto"]})
    else:
        raise RuntimeError("Tarea no reconocida")
    respuesta.raise_for_status()
    return respuesta.json()


def quitar_worker(c: Container) -> None:
    
    i = 0
    hallado = False

    while((i < len(workers)) and (not hallado)):

        if (workers[i] is c):
            del workers[i]
            hallado = True
        else:
            i += 1


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


#Esto es solo por modularizar
def pullear_imagen(imagen: str) -> None:
    try:
        pull_imagen(imagen, False)
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

# def obtener_puerto_libre(): -> int:
    # with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
