FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py render.py ./
COPY vendor ./vendor
COPY assets ./assets
COPY static ./static
ENV PYTHONUNBUFFERED=1 IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN useradd --uid 10001 --create-home appuser && chown -R appuser:appuser /app
USER appuser
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log"]
