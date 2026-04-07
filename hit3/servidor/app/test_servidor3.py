import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from docker.errors import APIError, ImageNotFound
from servidor import app, esperar_worker

client = TestClient(app)

PAYLOAD_VALIDO = {
    "imagen": "usuario/worker:v1",
    "tarea": "ocurrencias_palabras",
    "parametros": {},
    "datos": {"cuerpo_texto": "hola mundo hola"}
}


# --- Tarea no soportada ---

def test_tarea_no_soportada_retorna_fallo():
    payload = {**PAYLOAD_VALIDO, "tarea": "tarea_inexistente"}
    respuesta = client.post("/getRemoteTask", json=payload)
    assert respuesta.status_code == 200
    body = respuesta.json()
    assert body["estado"] == "error"
    assert "soportada" in body["mensaje"]


# --- Errores en pull_imagen ---

@patch("servidor.pull_imagen", side_effect=ImageNotFound("imagen no encontrada"))
def test_imagen_no_encontrada_retorna_fallo(mock_pull):
    respuesta = client.post("/getRemoteTask", json=PAYLOAD_VALIDO)
    body = respuesta.json()
    assert body["estado"] == "error"
    assert "encontrar" in body["mensaje"]


@patch("servidor.pull_imagen", side_effect=APIError("error de registry"))
def test_api_error_en_pull_retorna_fallo(mock_pull):
    respuesta = client.post("/getRemoteTask", json=PAYLOAD_VALIDO)
    body = respuesta.json()
    assert body["estado"] == "error"
    assert "pull" in body["mensaje"]


# --- Worker no disponible ---

@patch("servidor.pull_imagen")
@patch("servidor.levantar_worker")
@patch("servidor.esperar_worker", return_value=False)
def test_worker_no_disponible_retorna_fallo(mock_esperar, mock_levantar, mock_pull):
    mock_contenedor = MagicMock()
    mock_levantar.return_value = mock_contenedor

    respuesta = client.post("/getRemoteTask", json=PAYLOAD_VALIDO)
    body = respuesta.json()
    assert body["estado"] == "error"
    assert "disponible" in body["mensaje"]


# --- datos sin cuerpo_texto ---

@patch("servidor.pull_imagen")
@patch("servidor.levantar_worker")
@patch("servidor.esperar_worker", return_value=True)
def test_datos_sin_cuerpo_texto_retorna_fallo(mock_esperar, mock_levantar, mock_pull):
    mock_contenedor = MagicMock()
    mock_levantar.return_value = mock_contenedor

    payload = {**PAYLOAD_VALIDO, "datos": {}}
    respuesta = client.post("/getRemoteTask", json=payload)
    body = respuesta.json()
    assert body["estado"] == "error"
    assert "texto" in body["mensaje"]


# --- Tarea no reconocida dentro de ejecutar() ---

@patch("servidor.pull_imagen")
@patch("servidor.levantar_worker")
@patch("servidor.esperar_worker", return_value=True)
def test_tarea_no_reconocida_en_ejecutar_retorna_fallo(mock_esperar, mock_levantar, mock_pull):
    mock_contenedor = MagicMock()
    mock_levantar.return_value = mock_contenedor

    with patch("servidor.TAREAS", ["ocurrencias_palabras", "tarea_sin_implementar"]):
        payload = {**PAYLOAD_VALIDO, "tarea": "tarea_sin_implementar"}
        respuesta = client.post("/getRemoteTask", json=payload)
    body = respuesta.json()
    assert body["estado"] == "error"


# --- Flujo exitoso completo ---

@patch("servidor.pull_imagen")
@patch("servidor.levantar_worker")
@patch("servidor.esperar_worker", return_value=True)
@patch("servidor.ejecutar", return_value={"ocurrencias": {"hola": 2, "mundo": 1}})
def test_flujo_exitoso_retorna_resultado(mock_ejecutar, mock_esperar, mock_levantar, mock_pull):
    mock_contenedor = MagicMock()
    mock_levantar.return_value = mock_contenedor

    respuesta = client.post("/getRemoteTask", json=PAYLOAD_VALIDO)
    body = respuesta.json()
    assert body["estado"] == "ok"
    assert body["datos"]["ocurrencias"]["hola"] == 2
    assert body["datos"]["ocurrencias"]["mundo"] == 1


# --- destruir_worker se llama siempre (finally) ---

@patch("servidor.pull_imagen")
@patch("servidor.levantar_worker")
@patch("servidor.esperar_worker", return_value=True)
@patch("servidor.ejecutar", side_effect=RuntimeError("fallo inesperado"))
@patch("servidor.destruir_worker")
def test_destruir_worker_se_llama_ante_error(mock_destruir, mock_ejecutar, mock_esperar, mock_levantar, mock_pull):
    mock_contenedor = MagicMock()
    mock_levantar.return_value = mock_contenedor

    client.post("/getRemoteTask", json=PAYLOAD_VALIDO)
    mock_destruir.assert_called_once_with(mock_contenedor)


@patch("servidor.pull_imagen")
@patch("servidor.levantar_worker")
@patch("servidor.esperar_worker", return_value=True)
@patch("servidor.ejecutar", return_value={"ocurrencias": {}})
@patch("servidor.destruir_worker")
def test_destruir_worker_se_llama_en_exito(mock_destruir, mock_ejecutar, mock_esperar, mock_levantar, mock_pull):
    mock_contenedor = MagicMock()
    mock_levantar.return_value = mock_contenedor

    client.post("/getRemoteTask", json=PAYLOAD_VALIDO)
    mock_destruir.assert_called_once_with(mock_contenedor)


# --- esperar_worker: lógica de reintentos ---

@patch("servidor.time.sleep")
@patch("servidor.requests.get")
def test_esperar_worker_exito_en_primer_intento(mock_get, mock_sleep):
    mock_get.return_value = MagicMock(status_code=200)
    resultado = esperar_worker("http://worker_temp:5000/health", reintentos=5, delay=0.1)
    assert resultado is True
    mock_sleep.assert_not_called()


@patch("servidor.time.sleep")
@patch("servidor.requests.get", side_effect=Exception("connection refused"))
def test_esperar_worker_agota_reintentos_retorna_false(mock_get, mock_sleep):
    resultado = esperar_worker("http://worker_temp:5000/health", reintentos=4, delay=0.1)
    assert resultado is False
    assert mock_get.call_count == 4


@patch("servidor.time.sleep")
@patch("servidor.requests.get")
def test_esperar_worker_exito_tras_fallos_parciales(mock_get, mock_sleep):
    mock_get.side_effect = [
        Exception("connection refused"),
        Exception("connection refused"),
        MagicMock(status_code=200),
    ]
    resultado = esperar_worker("http://worker_temp:5000/health", reintentos=5, delay=0.1)
    assert resultado is True
    assert mock_get.call_count == 3
