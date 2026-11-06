# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
# Optional managed-cloud CA mount; verification always remains enabled.
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --no-cache-dir --require-hashes -r requirements.lock
RUN groupadd --gid 10001 jobpulse && useradd --uid 10001 --gid jobpulse --create-home jobpulse \
    && mkdir -p /app/data && chown jobpulse:jobpulse /app/data
COPY --chown=jobpulse:jobpulse . .
USER jobpulse
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
