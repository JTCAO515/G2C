FROM postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5
ARG CJ_RUNTIME_UID
RUN useradd --uid "$CJ_RUNTIME_UID" --no-create-home cj_runtime
COPY deploy/pg_hba.conf deploy/pg_ident.conf /etc/g2c/
