import pytest
import os
import threading
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

ENV = {
    "NODE_ID": "1",
    "MI_URL": "http://servidor1:8000",
    "MI_RED": "red_servidores",
    "PEERS": "http://servidor2:8000,http://servidor3:8000",
}


@pytest.fixture(autouse=True)
def patch_env_y_monitor():
    """
    Parchea las variables de entorno y el threading.Timer del módulo
    antes de importar servidor, para evitar que el monitor arranque
    durante los tests.
    """
    with patch.dict(os.environ, ENV):
        with patch("threading.Timer") as mock_timer:
            mock_timer.return_value = MagicMock()
            import importlib
            import servidor as srv
            importlib.reload(srv)
            srv.estado = srv.Estado()
            yield srv


@pytest.fixture()
def client(patch_env_y_monitor):
    srv = patch_env_y_monitor
    return TestClient(srv.app), srv


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_retorna_id_y_estado_inicial(client):
    c, srv = client
    respuesta = c.get("/health")
    assert respuesta.status_code == 200
    body = respuesta.json()
    assert body["id"] == 1
    assert body["ok"] is True
    assert body["lider_id"] is None
    assert body["en_eleccion"] is False


def test_health_refleja_lider_asignado(client):
    c, srv = client
    srv.estado.lider_id = 3
    srv.estado.lider_url = "http://servidor3:8000"
    with patch("socket.gethostbyname", return_value="172.18.0.4"):
        respuesta = c.get("/health")
    body = respuesta.json()
    assert body["lider_id"] == 3


def test_health_refleja_eleccion_en_curso(client):
    c, srv = client
    srv.estado.en_eleccion = True
    respuesta = c.get("/health")
    assert respuesta.json()["en_eleccion"] is True


# ---------------------------------------------------------------------------
# POST /election
# ---------------------------------------------------------------------------

def test_election_peer_menor_inicia_eleccion_y_retorna_ok(client):
    c, srv = client
    # NODE_ID=1, peer.id=0 → NODE_ID > peer.id → inicia elección
    with patch.object(srv, "iniciar_eleccion") as mock_eleccion:
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            respuesta = c.post("/election", json={"id_peer": 0, "url_peer": "http://servidor0:8000"})
    assert respuesta.status_code == 200
    assert respuesta.json()["ok"] is True


def test_election_peer_mayor_no_inicia_eleccion_y_retorna_false(client):
    c, srv = client
    # NODE_ID=1, peer.id=2 → NODE_ID < peer.id → no inicia elección
    with patch.object(srv, "iniciar_eleccion") as mock_eleccion:
        respuesta = c.post("/election", json={"id_peer": 2, "url_peer": "http://servidor2:8000"})
    assert respuesta.status_code == 200
    assert respuesta.json()["ok"] is False
    mock_eleccion.assert_not_called()


# ---------------------------------------------------------------------------
# POST /coordinator
# ---------------------------------------------------------------------------

def test_coordinator_actualiza_lider_id(client):
    c, srv = client
    respuesta = c.post("/coordinator", json={"id_peer": 3, "url_peer": "http://servidor3:8000"})
    assert respuesta.status_code == 200
    assert srv.estado.lider_id == 3


def test_coordinator_actualiza_lider_url(client):
    c, srv = client
    c.post("/coordinator", json={"id_peer": 2, "url_peer": "http://servidor2:8000"})
    assert srv.estado.lider_url == "http://servidor2:8000"


def test_coordinator_retorna_ok(client):
    c, srv = client
    respuesta = c.post("/coordinator", json={"id_peer": 2, "url_peer": "http://servidor2:8000"})
    assert respuesta.json()["ok"] is True


# ---------------------------------------------------------------------------
# iniciar_eleccion()
# ---------------------------------------------------------------------------

def test_iniciar_eleccion_sin_peers_mayores_declara_lider(patch_env_y_monitor):
    srv = patch_env_y_monitor
    # id_de_peer devuelve IDs menores que NODE_ID=1: ningún peer mayor
    with patch.object(srv, "id_de_peer", return_value=0):
        with patch.object(srv, "declarar_lider") as mock_declarar:
            with patch("requests.post"):
                srv.iniciar_eleccion()
    mock_declarar.assert_called_once()


def test_iniciar_eleccion_con_peer_mayor_no_declara_lider(patch_env_y_monitor):
    srv = patch_env_y_monitor
    # id_de_peer devuelve 2 → hay peers con ID mayor a NODE_ID=1
    with patch.object(srv, "id_de_peer", return_value=2):
        with patch.object(srv, "declarar_lider") as mock_declarar:
            with patch("requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                srv.iniciar_eleccion()
    mock_declarar.assert_not_called()


def test_iniciar_eleccion_no_corre_si_ya_hay_eleccion(patch_env_y_monitor):
    srv = patch_env_y_monitor
    srv.estado.en_eleccion = True
    with patch.object(srv, "declarar_lider") as mock_declarar:
        srv.iniciar_eleccion()
    mock_declarar.assert_not_called()


# ---------------------------------------------------------------------------
# declarar_lider()
# ---------------------------------------------------------------------------

def test_declarar_lider_actualiza_estado_local(patch_env_y_monitor):
    srv = patch_env_y_monitor
    with patch("requests.post"):
        srv.declarar_lider()
    assert srv.estado.lider_id == 1
    assert srv.estado.lider_url == "http://servidor1:8000"


def test_declarar_lider_notifica_a_peers(patch_env_y_monitor):
    srv = patch_env_y_monitor
    with patch("requests.post") as mock_post:
        srv.declarar_lider()
    assert mock_post.call_count == 2  # dos peers en ENV


def test_declarar_lider_tolera_peer_caido(patch_env_y_monitor):
    srv = patch_env_y_monitor
    with patch("requests.post", side_effect=Exception("connection refused")):
        srv.declarar_lider()  # no debe lanzar excepción
    assert srv.estado.lider_id == 1


# ---------------------------------------------------------------------------
# id_de_peer()
# ---------------------------------------------------------------------------

def test_id_de_peer_retorna_id_correcto(patch_env_y_monitor):
    srv = patch_env_y_monitor
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: {"id": 2})
        resultado = srv.id_de_peer("http://servidor2:8000")
    assert resultado == 2


def test_id_de_peer_retorna_menos_uno_si_peer_caido(patch_env_y_monitor):
    srv = patch_env_y_monitor
    with patch("requests.get", side_effect=Exception("timeout")):
        resultado = srv.id_de_peer("http://servidor2:8000")
    assert resultado == -1


# ---------------------------------------------------------------------------
# verificar_lider_elegido()
# ---------------------------------------------------------------------------

def test_verificar_lider_elegido_inicia_eleccion_si_no_hay_lider(patch_env_y_monitor):
    srv = patch_env_y_monitor
    srv.estado.lider_id = None
    with patch.object(srv, "iniciar_eleccion") as mock_eleccion:
        srv.verificar_lider_elegido()
    mock_eleccion.assert_called_once()


def test_verificar_lider_elegido_no_inicia_eleccion_si_hay_lider(patch_env_y_monitor):
    srv = patch_env_y_monitor
    srv.estado.lider_id = 3
    with patch.object(srv, "iniciar_eleccion") as mock_eleccion:
        srv.verificar_lider_elegido()
    mock_eleccion.assert_not_called()
