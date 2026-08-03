# syntax=docker/dockerfile:1

# ---- frontend build ----
FROM node:20-slim AS frontend
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- commit capture, so the health endpoint can report the running build ----
FROM alpine:3.20 AS commit
RUN apk add --no-cache git
WORKDIR /repo
COPY .git ./.git
RUN git rev-parse HEAD > /COMMIT_SHA

# ---- backend, serves the api and the built frontend from one origin ----
FROM python:3.11-slim AS final
WORKDIR /app
COPY api/pyproject.toml ./
COPY api/sabha ./sabha
RUN pip install --no-cache-dir .
COPY --from=frontend /web/dist ./static
COPY --from=commit /COMMIT_SHA ./COMMIT_SHA

ENV PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["sh", "-c", "uvicorn sabha.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
