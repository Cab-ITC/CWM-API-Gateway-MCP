# -----------------------------------------------------------------------------
#  Dockerfile for ConnectWise API Gateway MCP
# -----------------------------------------------------------------------------
FROM python:3.11-slim            # Small, modern Python base image

WORKDIR /app                     # All work happens in /app

# ----- install Python packages -----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----- copy the rest of the source code -----
COPY . .

ENV PYTHONUNBUFFERED=1           # Show logs immediately
EXPOSE 3333                      # Fly will route traffic here

# ----- start FastAPI with Uvicorn -----
# api_gateway_server:app  →  module : FastAPI instance
CMD ["uvicorn", "api_gateway_server:app", "--host", "0.0.0.0", "--port", "3333"]
