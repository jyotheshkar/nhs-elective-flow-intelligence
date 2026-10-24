FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt boto3==1.40.59
COPY backend /app/backend
COPY scripts /app/scripts
COPY config /app/config
COPY infra/aws/runtime.py /app/infra/aws/runtime.py
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/data/raw /app/data/processed && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "infra/aws/runtime.py", "serve"]
