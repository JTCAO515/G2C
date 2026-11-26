ARG JT_WORKBENCH_RUNTIME_IMAGE
FROM ${JT_WORKBENCH_RUNTIME_IMAGE}
WORKDIR /workbench
COPY jt/__init__.py ./jt/__init__.py
COPY jt/common/*.py ./jt/common/
COPY jt/synthetic/*.py ./jt/synthetic/
COPY jt/workbench/*.py jt/workbench/*.css jt/workbench/*.js ./jt/workbench/
COPY jt/workbench/migrations ./jt/workbench/migrations
ENV PYTHONPATH=/workbench PYTHONDONTWRITEBYTECODE=1
USER 10031:10031
RUN python -B -c "import jt.workbench.production"
ENTRYPOINT ["python", "-B", "-m", "jt.workbench.production"]
CMD ["serve"]
HEALTHCHECK --start-period=10s --interval=15s --timeout=5s CMD ["python", "-B", "-m", "jt.workbench.production", "healthcheck"]
