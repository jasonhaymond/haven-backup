FROM python:3.12-slim

# borgbackup from Debian's repo ships a working prebuilt binary -- building it
# from pip requires openssl/lz4/zstd dev headers and a compiler; apt is simpler
# and matches what most Borg servers already run. openssh-client is what
# BORG_RSH actually shells out to.
RUN apt-get update \
    && apt-get install -y --no-install-recommends borgbackup openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir borgmatic

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .

ENV HAVEN_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
