FROM python:3.12-slim

WORKDIR /app

COPY requisitos.txt .

RUN pip install --upgrade --no-cache-dir pip && pip install -r requisitos.txt --no-cache-dir

COPY ./app/ .

EXPOSE 8000

CMD ["uvicorn", "--host", "0.0.0.0", "--port", "8000", "servidor:app"]
