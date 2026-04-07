FROM python:3.12-slim

WORKDIR /app

COPY ./app/ .

COPY requisitos.txt .
RUN pip install --upgrade --no-cache-dir pip && pip install -r requisitos.txt --no-cache-dir

EXPOSE 5000

CMD ["uvicorn", "--host", "0.0.0.0", "--port", "5000", "worker:app"]
