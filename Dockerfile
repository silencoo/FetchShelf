# ---- 阶段 1: 构建器 (Builder) ----
FROM python:3.12-bullseye as builder

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
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

# ---- 阶段 2: 最终镜像 (Final Image) ----
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 添加元数据标签
LABEL name="DouK-Downloader" authors="JoeanAmier" repository="https://github.com/JoeanAmier/TikTokDownloader"

# 运行时使用 uv + 预构建虚拟环境
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

RUN pip install --no-cache-dir uv
COPY --from=builder /opt/venv /opt/venv

# 复制你的应用程序代码和相关文件
COPY src /app/src
COPY locale /app/locale
COPY static /app/static
COPY license /app/license
COPY main.py /app/main.py
COPY main_webui.py /app/main_webui.py
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock

# 暴露端口
EXPOSE 5555

# 创建挂载点
VOLUME /app/settings

# 设置容器启动命令（默认直接启动 WebUI 服务）
CMD ["uv", "run", "--no-sync", "main_webui.py"]
