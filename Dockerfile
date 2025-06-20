# -----------------------------------------------------------------------------
#  Dockerfile for ConnectWise API Gateway MCP
# -----------------------------------------------------------------------------
FROM python:3.11-slim

# work inside /app
WORKDIR /app

# ---------- install Python dependencies ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- copy application source ----------
COPY . .

# show logs immediately
ENV PYTHONUNBUFFERED=1

# port Fly will route to
EXPOSE 3333

# ---------- launch FastAPI with Uvicorn ----------
# module path : FastAPI instance  →  api_gateway_server:app
CMD ["uvicorn", "api_gateway_server:app", "--host", "0.0.0.0", "--port", "3333"]
