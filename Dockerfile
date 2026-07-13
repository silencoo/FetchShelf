# ---- 阶段 1: WebUI 构建器 ----
FROM node:22-bookworm-slim AS webui-builder

WORKDIR /app

COPY webui/package.json webui/package-lock.json /app/webui/
RUN npm ci --prefix /app/webui

COPY webui /app/webui
RUN npm run build --prefix /app/webui

# ---- 阶段 2: Python 构建器 ----
FROM python:3.12-bullseye AS builder

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 使用 uv 同步依赖到固定虚拟环境目录
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
COPY vendor/TikTok-Api /app/vendor/TikTok-Api
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

# ---- 阶段 3: 最终镜像 (Final Image) ----
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 运行时使用 uv + 预构建虚拟环境
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    xvfb \
    xauth \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo-gobject2 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libsm6 \
    libu2f-udev \
    libxext6 \
    libxrender1 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxkbcommon0 \
    libxrandr2 \
    libxcb-util1 \
    libxcb-render0 \
    libxcb-shm0 \
    libxfixes3 \
    libxi6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/* \
    && ldconfig \
    && ldconfig -p | grep -q "libxcb.so.1" \
    && pip install --no-cache-dir uv
COPY --from=builder /opt/venv /opt/venv
RUN python -m playwright install chromium webkit

# 复制你的应用程序代码和相关文件
COPY src /app/src
COPY --from=webui-builder /app/src/webui/static /app/src/webui/static
COPY vendor /app/vendor
COPY locale /app/locale
COPY static /app/static
COPY license /app/license
COPY main.py /app/main.py
COPY main_webui.py /app/main_webui.py
COPY encipher_example.py /app/encipher_example.py
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock

# 暴露端口
EXPOSE 5555

# 创建挂载点
VOLUME ["/app/settings", "/app/downloads"]

# 设置容器启动命令（默认直接启动 WebUI 服务）
CMD ["python", "main_webui.py"]
