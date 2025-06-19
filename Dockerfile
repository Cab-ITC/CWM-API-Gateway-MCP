# Use a slim Python image to keep the container small
FROM python:3.11-slim

# Create and switch to /app inside the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project files
COPY . .

# Ensure all Python output appears immediately in logs
ENV PYTHONUNBUFFERED=1

# Expose the port the MCP server listens on
EXPOSE 3333

# Start the server
CMD ["python", "api_gateway_server.py"]
