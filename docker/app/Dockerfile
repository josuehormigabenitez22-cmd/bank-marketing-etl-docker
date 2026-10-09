# Imagen ligera para ejecutar el ETL y los tests.
# El código se monta como volumen en el docker-compose.yml, no se copia a la imagen
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTEST_ADDOPTS="-o cache_dir=/tmp/.pytest_cache"

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

CMD ["python", "-m", "src.etl"]
