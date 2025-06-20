# -----------------------------------------------------------------------------
#  Dockerfile for ConnectWise API Gateway MCP
# -----------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# ---------- install Python dependencies ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- copy application source ----------
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 3333

# ---------- launch FastAPI with Uvicorn ----------
# (module path : FastAPI instance)  →  api_gateway.main:app   ← adjust if different
CMD ["uvicorn", "api_gateway.main:app", "--host", "0.0.0.0", "--port", "3333"]
