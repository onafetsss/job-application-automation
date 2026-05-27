FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install uv
CMD ["python", "main.py"]
