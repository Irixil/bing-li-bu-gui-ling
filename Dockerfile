FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_MODE=local_first \
    API_HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser

COPY backend ./backend
COPY config ./config
COPY prompts ./prompts

USER appuser
EXPOSE 8000
CMD ["python", "-m", "backend.server"]
