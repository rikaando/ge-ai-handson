FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app

COPY --chown=appuser:appuser audit_agent ./audit_agent
COPY --chown=appuser:appuser agent_card.template.json ./agent_card.template.json
COPY --chown=appuser:appuser main.py ./main.py
RUN test -f /app/audit_agent/data/users.csv && test -f /app/audit_agent/data/ai_audit_logs.csv

USER appuser
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
