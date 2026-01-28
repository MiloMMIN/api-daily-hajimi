FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

WORKDIR /app

# Ensure output is sent directly to terminal (docker logs) without buffering
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./main.py

CMD ["python", "main.py"]
