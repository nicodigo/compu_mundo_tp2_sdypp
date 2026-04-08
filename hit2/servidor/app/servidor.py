from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Container, Dict
from docker.models.containers import Container
from docker.errors import APIError, ImageNotFound
import requests
import docker
import time
import threading
from queue import Queue
import os


app = FastAPI()

TAREAS = ["ocurrencias_palabras",
          ]
cliente = docker.from_env()

MAX_WORKERS = int(os.getenv("MAX_WORKERS", 4))
semaforo_workers = threading.Semaphore(MAX_WORKERS)

cola_tareas = Queue(maxsize=50)

clock: int = 0
clock_lock = threading.Lock()

contador_tareas: int = 0
contador_lock = threading.Lock()

REINTENTOS_MAX_TAREA = 2


def worker_loop():
    while True:
        tarea_interna: Tarea= cola_tareas.get()

        with semaforo_workers:
            try:
                resultado: Resultado = ejecutar_tarea_remota(tarea_interna.tarea_remota, tarea_interna.tarea_id)
                tarea_interna.resultado = resultado
                tarea_interna.estado = "completada"
                tarea_interna.evento.set()
            except Exception as e:
                print(e)
                tarea_interna.estado = "error"
                tarea_interna.reintentos += 1
                if tarea_interna.reintentos > REINTENTOS_MAX_TAREA:
                    tarea_interna.evento.set()
                else:
                    try:
                        cola_tareas.put(tarea_interna, block=False)
                    except:
                        tarea_interna.evento.set()
            finally:
                cola_tareas.task_done()


for _ in range(MAX_WORKERS):
    threading.Thread(target=worker_loop,
                     daemon=True).start()

class TareaRemota(BaseModel):
    imagen: str
    tarea: str
    parametros: Dict[str, Any]
    datos: Dict[str, Any]


class Resultado(BaseModel):
    estado: str
    datos: Dict[str, Any] | None = None


class Tarea():
    def __init__(self, tarea_id, timestamp, tarea_remota, evento):
        self.tarea_id: int = tarea_id
        self.timestamp: int = timestamp
        self.tarea_remota: TareaRemota = tarea_remota

        self.estado: str = "pendiente"
        self.reintentos: int = 0
        self.resultado: Resultado | None = None
        self.evento = evento


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
def recibir_nueva_tarea(tarea: TareaRemota) -> Resultado | Fallo:
    print("ENTRO AL ENDPOINT", flush=True)
    if (tarea.tarea not in TAREAS):
        return Fallo(estado="error",
                     mensaje="La tarea no está soportada",
                     )
    print("tarea existe")

    try:
        pull_imagen(tarea.imagen, True)
    except ImageNotFound:
        return Fallo(estado="error",
                     mensaje="La imagen no se pudo encontrar",
                     )
    except APIError:
        # print(f"error al hacer pull: {e}")
        return Fallo(estado="error",
                     mensaje="Problema al hacer pull de la imagen",
                     )
    print("imagen pulleada")

    tarea_interna: Tarea = generar_tarea_interna(tarea)

    try:
        cola_tareas.put(tarea_interna, block=False)
    except:
        return Fallo(estado="error",
                     mensaje="Cola de tareas llena",
                     )

    if not tarea_interna.evento.wait(timeout=30):
        return Fallo(estado= "error",
                     mensaje= "La tarea no pudo ser completada TIMEOUT",
                     )

    if tarea_interna.estado != "completada":
        return Fallo(estado= "error",
                     mensaje= "La tarea no pudo ser completada",
                     )
    if tarea_interna.resultado is None:
        return Fallo(estado= "error",
                     mensaje= "La tarea no devolvio informacion",
                     )

    return tarea_interna.resultado




def generar_id_tarea() -> int:
    global contador_tareas
    with contador_lock:
        contador_tareas += 1
        return contador_tareas


def get_lamport():
    global clock
    with clock_lock:
        clock += 1
        return clock


def generar_tarea_interna(tarea: TareaRemota) -> Tarea:
    id_tarea: int = generar_id_tarea()
    timestamp_tarea: int = get_lamport()

    tarea_interna: Tarea = Tarea(tarea_id=id_tarea,
                                 timestamp=timestamp_tarea,
                                 tarea_remota=tarea,
                                 evento=threading.Event(),
                                 )
    return tarea_interna


def levantar_worker(imagen: str, id_worker: int) -> Container:
    contenedor: Container = cliente.containers.run(
            imagen,
            name=f"worker{id_worker}",
            detach=True,
            network="mi_red",
            )
    return contenedor


def esperar_worker(url: str, reintentos: int = 10, delay: float = 0.5) -> bool:
    for _ in range(reintentos):
        try:
            requests.get(url)
            return True
        except:
            time.sleep(delay)
    return False


def ejecutar(url_base: str, tarea: TareaRemota) -> Dict[str, Any]:
    respuesta: requests.Response
    if tarea.tarea == "ocurrencias_palabras":
        if not tarea.datos.get("cuerpo_texto"):
            raise RuntimeError("No se encontro texto a contar")
        respuesta = requests.put(f"{url_base}/contar_palabras", json={"cuerpo_texto": tarea.datos["cuerpo_texto"]})
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


def ejecutar_tarea_remota(tarea: TareaRemota, id_tarea) -> Resultado:
    contenedor = levantar_worker(tarea.imagen, id_worker=id_tarea)
    print("worker levantado")
    try:
        contenedor.reload() # type: ignore
        # puerto = int(contenedor.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]) # type: ignore
        url_base: str = f"http://worker{id_tarea}:5000"

        if not esperar_worker(f"{url_base}/health"):
            raise RuntimeError("worker no disponible")
        print("worker activo")

        datos_resultado: Dict[str, Any] = ejecutar(url_base, tarea)
        print(f"resultados: {datos_resultado}")
        return Resultado(estado="ok",
                         datos=datos_resultado,
                         )
    except Exception as e:
        raise e
    finally:
        destruir_worker(contenedor)
