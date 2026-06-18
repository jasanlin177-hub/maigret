FROM python:3.11-slim AS base
LABEL maintainer="Soxoj <soxoj@protonmail.com>"
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip poetry-core
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
      build-essential \
      python3-dev \
      pkg-config \
      libcairo2-dev \
      libxml2-dev \
      libxslt1-dev \
    && rm -rf /var/lib/apt/lists/* /tmp/*
COPY . .
RUN YARL_NO_EXTENSIONS=1 python3 -m pip install --no-cache-dir .
# For production use, set FLASK_HOST to a specific IP address for security
ENV FLASK_HOST=0.0.0.0

# CLI variant
FROM base AS cli
ENTRYPOINT ["maigret"]

# Web UI variant (default): auto-launches the web interface on $PORT
FROM base AS web
# openpyxl 供 Excel 報告下載；PDF 改用瀏覽器列印 HTML 報告，不再裝 [pdf]
RUN pip install --no-cache-dir openpyxl
ENV PORT=5000
EXPOSE 5000
ENTRYPOINT ["sh", "-c", "exec maigret --web \"$PORT\""]
