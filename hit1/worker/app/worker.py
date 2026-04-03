from fastapi import FastAPI
from collections import Counter
import re
from pydantic import BaseModel

app = FastAPI()


class Texto(BaseModel):
    cuerpo_texto: str

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.put("/contar_palabras")
def contar_palabras(texto: Texto):
    tratado: str = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ]', ' ', texto.cuerpo_texto)
    tratado = tratado.lower()
    palabras = tratado.split()
    ocurrencias_palabras = Counter(palabras)
    return {"ocurrencias": ocurrencias_palabras}
