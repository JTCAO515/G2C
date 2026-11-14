ARG CJ_BETA_IMAGE
FROM ${CJ_BETA_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-17 \
    && pg_dropcluster --stop 17 main \
    && rm -rf /var/lib/apt/lists/*
USER cj
