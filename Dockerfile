FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Solo las dependencias (capa cacheada); el código se ejecuta desde /srv
COPY pyproject.toml README.md LICENSE ./
COPY app/__init__.py app/__init__.py
RUN pip install . && pip uninstall -y extractor-facturas

COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY ui ui
COPY eval/dataset/factura_010.pdf eval/dataset/factura_010.pdf

RUN useradd --create-home appuser
USER appuser

ENV PORT=8000
EXPOSE 8000

# La API aplica las migraciones al arrancar. La UI sobrescribe el comando.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
