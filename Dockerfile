# --- Stage 1: Build Stage ---
FROM python:3.11-slim AS builder

WORKDIR /app

# Install compilers needed for some python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies into a local folder
RUN pip3 install --user --no-cache-dir -r requirements.txt


# --- Stage 2: Final Runtime Stage ---
FROM python:3.11-slim

WORKDIR /app

# Only install curl for the healthcheck, no compilers here!
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the installed python libraries from the builder
COPY --from=builder /root/.local /root/.local
COPY app.py .

# Ensure the local bin is in the path so streamlit can run
ENV PATH=/root/.local/bin:$PATH
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

EXPOSE 8501


ENTRYPOINT ["streamlit", "run", "app.py"]