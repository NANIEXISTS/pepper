FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md config.yaml ./
COPY trading_ai ./trading_ai

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "trading_ai.main"]
