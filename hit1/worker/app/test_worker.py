import pytest
from fastapi.testclient import TestClient
from worker import app

client = TestClient(app)


# --- /health ---

def test_health_retorna_ok():
    respuesta = client.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


# --- /contar_palabras ---

def test_conteo_palabras_repetidas():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "hola hola mundo"})
    assert respuesta.status_code == 200
    ocurrencias = respuesta.json()["ocurrencias"]
    assert ocurrencias["hola"] == 2
    assert ocurrencias["mundo"] == 1


def test_elimina_signos_de_puntuacion():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "hola, hola. mundo!"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert ocurrencias["hola"] == 2
    assert ocurrencias["mundo"] == 1
    assert "," not in ocurrencias
    assert "." not in ocurrencias


def test_elimina_numeros():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "hola 123 mundo 456"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert "123" not in ocurrencias
    assert "456" not in ocurrencias
    assert ocurrencias["hola"] == 1
    assert ocurrencias["mundo"] == 1


def test_preserva_tildes():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "canción canción"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert ocurrencias["canción"] == 2


def test_preserva_enye():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "niño niño niña"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert ocurrencias["niño"] == 2
    assert ocurrencias["niña"] == 1


def test_insensible_a_mayusculas():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "Hola hola HOLA"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert ocurrencias["hola"] == 3


def test_texto_vacio_retorna_diccionario_vacio():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": ""})
    assert respuesta.status_code == 200
    assert respuesta.json()["ocurrencias"] == {}


def test_solo_caracteres_no_alfabeticos_retorna_diccionario_vacio():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "123 !!! @@@ ..."})
    assert respuesta.status_code == 200
    assert respuesta.json()["ocurrencias"] == {}


def test_palabra_unica_cuenta_una_vez():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "python"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert ocurrencias["python"] == 1


def test_multiples_espacios_no_generan_entradas_vacias():
    respuesta = client.put("/contar_palabras", json={"cuerpo_texto": "hola   mundo"})
    ocurrencias = respuesta.json()["ocurrencias"]
    assert "" not in ocurrencias
    assert ocurrencias["hola"] == 1
    assert ocurrencias["mundo"] == 1
