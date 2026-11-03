FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EMPORIO_DB_PATH=/data/emporio.db

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
# Editable, so the project root (and its data folder) is /app, as in a normal checkout.
RUN python -m pip install --no-cache-dir -e .

# Not root; the conversations and tickets live in a volume.
RUN useradd --create-home melo && mkdir -p /data && chown melo /data
USER melo
VOLUME ["/data"]

# The key is passed when the container runs (docker run -it --env-file .env ...), never baked in.
ENTRYPOINT ["emporio"]
CMD ["chat"]
