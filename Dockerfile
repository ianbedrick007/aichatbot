# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Optimize Python environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user
ARG UID=10001
RUN adduser --disabled-password --gecos "" --uid "${UID}" appuser

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=appuser:appuser . .

# Ensure media directories exist (empty dirs aren't tracked by git)
RUN mkdir -p /app/media/product_pics /app/media/products && chown -R appuser:appuser /app/media

# Use non-privileged user
USER appuser

# Expose application port
EXPOSE 8080

# Start the application
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]