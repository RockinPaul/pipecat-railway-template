FROM node:22.22.0-bookworm-slim AS client
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY client.js ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.6 AS uv
FROM python:3.12.14-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server.py bot.py providers.py speech.py ./
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY static/ ./static/
COPY --from=client /build/static/app.js ./static/app.js
RUN .venv/bin/python bot.py --check && useradd --system --uid 10001 app
USER app
CMD ["/app/.venv/bin/python", "server.py"]
