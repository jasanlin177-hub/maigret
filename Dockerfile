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
# Pillow 供頭像關聯分析（dHash 計算）；tzdata 供臺灣時區顯示
RUN pip install --no-cache-dir openpyxl Pillow tzdata
ENV PORT=5000
EXPOSE 5000
# --no-autoupdate：停用內建的 24 小時自動更新資料庫機制。
# 該機制會從 upstream soxoj/maigret（非本 fork）下載官方站點資料庫並
# 快取於 ~/.maigret/data.json，一旦觸發就會整份覆蓋掉本 fork 客製的
# 臺灣站點（如蝦皮 ShopeeTW）與手動啟用的站點設定，且沒有任何告警。
# 之後如需同步 upstream 的站點修補，應改為手動比對合併，而非讓它自動整份覆蓋。
ENTRYPOINT ["sh", "-c", "exec maigret --web \"$PORT\" --no-autoupdate"]
