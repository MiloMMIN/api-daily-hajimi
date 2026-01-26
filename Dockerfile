FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./main.py
COPY accounts.example.json ./accounts.example.json
COPY config.example.jsonc ./config.example.jsonc

CMD ["python", "main.py"]
