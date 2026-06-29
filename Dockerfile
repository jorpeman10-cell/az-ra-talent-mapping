FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY . .

EXPOSE 8810

CMD ["python", "-m", "uvicorn", "api.bridge:app", "--host", "0.0.0.0", "--port", "8810"]
