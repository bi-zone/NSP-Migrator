# =============================================================================
# STAGE DEPENDENCY GRAPH
#
# python-base
# │
# ├──> build-base
# │    ├──> api-deps
# │    │    └──> api-dev-deps
# │    │
# │    └──> streamlit-deps
# │         └──> streamlit-dev-deps
# │
# └──> app-base
#      ├──> api            <·· .venv from api-deps
#      ├──> api-dev        <·· .venv from api-dev-deps
#      ├──> streamlit      <·· .venv from streamlit-deps
#      └──> streamlit-dev  <·· .venv from streamlit-dev-deps
#
# =============================================================================

ARG PYTHON_IMAGE
ARG POETRY_VERSION=2.1.2


# -----------------------------------------------------------------------------
# Common Python runtime base
# -----------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

RUN apk add --no-cache curl


# -----------------------------------------------------------------------------
# Dependency builder
# -----------------------------------------------------------------------------
FROM python-base AS build-base

ARG POETRY_VERSION

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true

RUN apk add --no-cache build-base \
    && pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./


# -----------------------------------------------------------------------------
# Production dependencies
# -----------------------------------------------------------------------------
FROM build-base AS api-deps

RUN poetry install --only main --no-root


FROM api-deps AS streamlit-deps

RUN poetry install --with streamlit --no-root


# -----------------------------------------------------------------------------
# Development dependencies
# -----------------------------------------------------------------------------
FROM api-deps AS api-dev-deps

RUN poetry install --with dev --no-root


FROM streamlit-deps AS streamlit-dev-deps

RUN poetry install --with dev --no-root


# -----------------------------------------------------------------------------
# Common application source
# -----------------------------------------------------------------------------
FROM python-base AS app-base

COPY src ./src
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations


# -----------------------------------------------------------------------------
# FastAPI production
# -----------------------------------------------------------------------------
FROM app-base AS api

COPY --from=api-deps /app/.venv /app/.venv

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD [ \
    "uvicorn", \
    "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1" \
]


# -----------------------------------------------------------------------------
# FastAPI development
# -----------------------------------------------------------------------------
FROM app-base AS api-dev

COPY --from=api-dev-deps /app/.venv /app/.venv
COPY tests ./tests
COPY docs ./docs
COPY scripts ./scripts

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD [ \
    "uvicorn", \
    "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--reload", \
    "--reload-dir", "/app/src" \
]


# -----------------------------------------------------------------------------
# Streamlit production
# -----------------------------------------------------------------------------
FROM app-base AS streamlit

COPY --from=streamlit-deps /app/.venv /app/.venv
COPY .streamlit ./.streamlit

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD [ \
    "streamlit", \
    "run", \
    "src/streamlit_app/Home.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false" \
]


# -----------------------------------------------------------------------------
# Streamlit development
# -----------------------------------------------------------------------------
FROM app-base AS streamlit-dev

COPY --from=streamlit-dev-deps /app/.venv /app/.venv
COPY .streamlit ./.streamlit
COPY tests ./tests
COPY docs ./docs
COPY scripts ./scripts

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD [ \
    "streamlit", \
    "run", \
    "src/streamlit_app/Home.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false" \
]