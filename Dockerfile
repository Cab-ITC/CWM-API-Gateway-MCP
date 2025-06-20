# -----------------------------------------------------------------------------
#  Dockerfile for ConnectWise API Gateway MCP
# -----------------------------------------------------------------------------
FROM python:3.11-slim            # small base image

WORKDIR /app                      # work inside /app

# ---------- install Python dependencies ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- copy application source ----------
COPY . .

ENV PYTHONUNBUFFERED=1            # make logs appear immediately
EXPOSE 3333                       # port Fly will route to

# ---------- launch FastAPI ------------------------
#  "api_gateway_server:app"  =>  module path : FastAPI instance
CMD ["uvicorn", "api_gateway_server:app", "--host", "0.0.0.0", "--port", "3333"]
