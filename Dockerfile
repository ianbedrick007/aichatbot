FROM python:3.11-slim

WORKDIR /fastwebapp

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run sets PORT=8080 automatically
ENV PORT=8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]