FROM python:3.9-slim as base

ARG user_no=1000

COPY ./ /opt/backup-restore-server/

USER 0:0
RUN chown -R ${user_no}:${user_no} /opt/backup-restore-server/
USER ${user_no}:${user_no}

# ---------------------------------------------------------------------------------
# for development
FROM base AS dev

WORKDIR /opt/backup-restore-server
RUN which python && \
    python -m pip install -e . --no-cache-dir

WORKDIR /var/lib/backup-restore
# ---------------------------------------------------------------------------------
