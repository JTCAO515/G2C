FROM python:3.14-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.14
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY scripts ./scripts
COPY deploy ./deploy
COPY eval/optimization/cases.v2.json eval/optimization/score_v2.py ./eval/optimization/
COPY tooling/optimization/uv.lock ./tooling/optimization/uv.lock
RUN uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app:/app/scripts" PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home cj
USER cj
ENTRYPOINT ["python", "-B", "-m", "deploy.entrypoint"]
