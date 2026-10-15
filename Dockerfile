FROM python:3.13-slim

WORKDIR /app

# Copiar requirements primero para aprovechar cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Crear usuario no-root para seguridad
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Exponer puerto 8080 (requerido por Cloud Run)
EXPOSE 8080

# Cloud Run entrega el puerto en $PORT
# En la demo publicada, primero copia la base y los archivos de partida (ver scripts/cargar_semilla.py)
CMD python scripts/cargar_semilla.py && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
