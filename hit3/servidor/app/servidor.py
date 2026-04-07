from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Container, Dict
from docker.models.containers import Container
from docker.errors import APIError, ImageNotFound
import requests
import docker
import time
import os
import threading
import socket
from urllib.parse import urlparse


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


class Estado(BaseModel):
    lider_id: int | None = None
    lider_url: str | None = None
    en_eleccion: bool = False


class Peer(BaseModel):
    id_peer: int
    url_peer: str


app = FastAPI()

TAREAS = ["ocurrencias_palabras",
          ]

cliente = docker.from_env()

lock = threading.Lock()

NODE_ID = int(os.getenv("NODE_ID", "-1"))
PEERS = os.getenv("PEERS", " ").split(",")
MI_URL = os.getenv("MI_URL")
MI_RED = os.getenv("MI_RED")

estado = Estado()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/tareas_soportadas")
def devolver_tareas():
    return{"tareas_soportadas": TAREAS}


@app.get("/health")
def devolver_health():
    url_lider: str | None = None
    if estado.lider_url is not None:
        dominio = urlparse(estado.lider_url).hostname
        if dominio is not None:
            url_lider = socket.gethostbyname(dominio)

    return{"id": NODE_ID,
           "ok": True,
           "lider_id": estado.lider_id,
           "lider_url": url_lider,
           "en_eleccion": estado.en_eleccion,
           }


@app.post("/election")
def recibir_eleccion(peer: Peer):
    if NODE_ID > peer.id_peer:
        threading.Thread(target=iniciar_eleccion).start()
        return {"ok": True}
    return {"ok": False}


@app.post("/coordinator")
def recibir_coordinador(peer: Peer):
    with lock:
        estado.lider_id = peer.id_peer
        estado.lider_url = peer.url_peer
    return {"ok": True}


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
        contenedor.reload() # type: ignore
        # puerto = int(contenedor.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]) # type: ignore
        url_base: str = f"http://worker_temp:5000"

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
            detach=True,
            network=MI_RED,
            name="worker_temp",
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

def iniciar_eleccion():
    global PEERS
    global NODE_ID
    global estado

    with lock:
        if estado.en_eleccion:
            return
        estado.en_eleccion = True

    peers_mayores = [p for p in PEERS if id_de_peer(p) > NODE_ID]
    print(peers_mayores)

    respuestas = []
    for peer in peers_mayores:
        try:
            r = requests.post(f"{peer}/election", json={"id_peer": NODE_ID, "url_peer": MI_URL}, timeout=1)
            if r.status_code== 200:
                respuestas.append(peer)
        except requests.RequestException:
            pass

    print(f"{NODE_ID}, soy lider?")
    if not respuestas:
        print(f"SI!!! yo {NODE_ID}, me declaro lider")
        declarar_lider()
    else:
        threading.Timer(7.0, verificar_lider_elegido).start()

    with lock:
        estado.en_eleccion = False


def declarar_lider():
    with lock:
        estado.lider_id = NODE_ID
        estado.lider_url = MI_URL

    for peer in PEERS:
        try:
            requests.post(f"{peer}/coordinator",
                          json={"id_peer": NODE_ID, "url_peer": MI_URL},
                          timeout=1)
            print(f"yo {NODE_ID}, me declaro como lider a {peer}")
        except requests.RequestException:
            pass


def id_de_peer(peer: str) -> int:
    try:
        respuesta = requests.get(f"{peer}/health", timeout=1).json()
        peer_id = respuesta.get("id")
        return peer_id
    except requests.RequestException:
        return -1


def verificar_lider_elegido():
    with lock:
        if estado.lider_id is None or estado.lider_id == NODE_ID:
            iniciar_eleccion()


def monitorear_lider():
    while True:
        time.sleep(2)
        if estado.lider_id == NODE_ID:
            continue
        lider_url = estado.lider_url

        if not lider_url:
            iniciar_eleccion()
            continue
        try:
            requests.get(f"{lider_url}/health", timeout=2)
        except requests.RequestException:
            iniciar_eleccion()

threading.Timer(5.0,
                monitorear_lider,
                 ).start()
