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

# ---------- launch the MCP server ----------
# Run the CLI entry point directly instead of using Uvicorn
CMD ["python", "api_gateway_server.py"]
