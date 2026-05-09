FROM python:3.11-slim

WORKDIR /app

RUN pip install flask --quiet

COPY server.py .
COPY public/ ./public/

EXPOSE 5052

CMD ["python", "server.py"]