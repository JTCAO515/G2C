ARG CJ_HK_OPERATOR_IMAGE
FROM ${CJ_HK_OPERATOR_IMAGE}
# Existing B image supplies Python, PG17 and business code; no new service.
COPY eval /app/eval
COPY evaluation /app/evaluation
COPY c-eval-source.json /app/c-eval-source.json
ENTRYPOINT ["python", "-B", "/app/eval/hk.py", "run"]
