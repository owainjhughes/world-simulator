FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs libs
COPY services/genesis services/genesis

RUN uv sync --package genesis --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "genesis.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
