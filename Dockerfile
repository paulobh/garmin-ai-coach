FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (build-essential and curl for native builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and default configs
COPY src/ ./src/
COPY config/users.yaml.example ./config/users.yaml.example
COPY config/config.yaml.example ./config/config.yaml.example

# Create mount points
RUN mkdir -p /app/data /app/config

# Expose Streamlit port
EXPOSE 8502

# Default command: run unified stack (Web dashboard + Scheduler + Telegram)
CMD ["python", "-m", "src.main", "--mode", "all"]
