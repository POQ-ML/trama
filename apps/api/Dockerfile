FROM python:3.11-slim

WORKDIR /app

# Contexto de build = raiz do monorepo (ver docker-compose.yml).
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/ .
# Migrations vivem em database/migrations; o alembic.ini resolve
# version_locations como %(here)s/../../database -> /database na imagem.
COPY database/migrations/ /database/migrations/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
