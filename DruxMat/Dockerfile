FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DRUXMAT_DATA_DIR=/data DRUXMAT_PRODUCTION=1
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py setup_admin.py entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh
COPY templates ./templates
COPY static ./static
RUN useradd -m -u 10001 druxmat && mkdir -p /data && chown druxmat:druxmat /data
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["/bin/sh", "-c", "exec gunicorn --workers 1 --bind 0.0.0.0:${PORT:-8000} --timeout 60 app:app"]
