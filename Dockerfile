# -----------------------------------------------------------------------------
#  Dockerfile for ConnectWise API Gateway MCP (Python version)
# -----------------------------------------------------------------------------

# 1. Use a small, recent Python base image
FROM python:3.11-slim

# 2. Create a working directory inside the container
WORKDIR /app

# 3. Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of the project files into the container
COPY . .

# 5. Ensure logs appear immediately (no buffering)
ENV PYTHONUNBUFFERED=1

# 6. Expose the port the server will listen on
EXPOSE 3333

# 7. Start the FastAPI server with Uvicorn
#    - "api_gateway_server:app"  →  module path : FastAPI instance
#    - "--host 0.0.0.0"         →  listen on all interfaces (required by Fly)
#    - "--port 3333"            →  must match Fly’s internal port
CMD ["uvicorn", "api_gateway_server:app", "--host", "0.0.0.0", "--port", "3333"]
