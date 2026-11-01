FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 traderoom
COPY app.py trade_valuator.py fantasy_lib.py version.py VERSION ./
COPY evaluator ./evaluator
COPY static ./static
COPY fixtures ./fixtures
COPY scripts/local.py scripts/container_start.py ./scripts/
USER traderoom
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).read()"
CMD ["python", "app.py", "--host", "0.0.0.0", "--allowed-host", "localhost"]
