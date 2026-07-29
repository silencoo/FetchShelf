# FetchShelf

面向 Docker 的抖音 / TikTok 采集、下载和媒体管理工具

> [!IMPORTANT]
> 当前项目以 **Docker Compose + WebUI** 为主要部署、测试和维护方式。Windows / macOS
> 可执行文件与传统终端交互模式属于历史入口，不再作为主要发行与支持目标。

## 项目简介

FetchShelf 用于在自己的设备上管理抖音和 TikTok 公开内容采集任务。它更适合作为
长期运行的 Docker 服务，而不是一次性的桌面下载器。

WebUI 目前提供的主要能力：

- 管理抖音与 TikTok 账号，批量采集发布、喜欢、收藏等内容
- 将多个账号合并为一个批量任务，并配置每日定时采集
- 查看任务进度、单账号结果以及暂停、继续和停止状态
- 通过账户看板搜索、排序并查看每个目标的最近作品和最近采集时间
- 在媒体库中分页浏览目录，以瀑布流、缩略图和 Lightbox 预览图片或视频
- 管理配置、Cookie、采集身份、代理和账号路由
- 通过 FastAPI 文档调用 Web API

## 维护状态

| 使用方式 | 状态 | 说明 |
| --- | --- | --- |
| Docker Compose | 主要维护 | 推荐用于正式部署 |
| Docker 本机构建 | 主要维护 | 仓库默认方式，不依赖预构建镜像 |
| WebUI | 主要维护 | 当前主要操作界面 |
| Web API | 维护中 | 启动后访问 `/docs` |
| 源码终端模式 | 兼容保留 | 适合调试或高级用途 |
| Windows / macOS 可执行文件 | 非主要维护 | 不保证持续构建、兼容性或功能同步 |

## 快速开始

### 1. 准备环境

需要安装：

- Git
- Docker Engine 或 Docker Desktop
- Docker Compose v2（使用 `docker compose` 命令）

克隆仓库：

```bash
git clone https://github.com/silencoo/FetchShelf.git
cd FetchShelf
```

### 2. 创建环境配置

```bash
cp .env.example .env
```

为 WebUI Token 和身份加密密钥生成两个不同的随机值：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

编辑 `.env`：

```dotenv
TZ=Asia/Shanghai
WEBUI_PORT=5555
SETTINGS_DIR=./settings
DOWNLOADS_DIR=./downloads
FETCHSHELF_API_TOKEN=替换为第一个随机值
FETCHSHELF_IDENTITY_KEY=替换为第二个随机值
```

正式部署建议为持久化目录使用绝对路径，例如：

```dotenv
SETTINGS_DIR=/srv/fetchshelf/settings
DOWNLOADS_DIR=/srv/fetchshelf/downloads
```

不要把 `.env`、Cookie、Token 或身份加密密钥提交到 Git。

### 3. 构建并启动

```bash
docker compose up -d --build
docker compose ps
```

首次构建需要下载 Python、Node、Chromium 和 ffmpeg 相关依赖，耗时取决于网络和设备性能。

### 4. 打开 WebUI

浏览器访问：

```text
http://主机IP:5555/ui
```

在 WebUI 中输入 `.env` 里的 `FETCHSHELF_API_TOKEN`。首次启动后还需要：

1. 打开“设置”
2. 将下载根目录 `root` 设置为 `/app/downloads`
3. 保存配置
4. 按需添加账号、定时任务和采集身份

如果修改了 `WEBUI_PORT`，请使用对应端口访问。

## 持久化目录

容器本身可以随时重建，真正需要保护的是以下宿主机数据：

| 宿主机配置 | 容器路径 | 内容 |
| --- | --- | --- |
| `SETTINGS_DIR` | `/app/settings` | `settings.json`、数据库、任务记录、缓存、账户头像等 |
| `DOWNLOADS_DIR` | `/app/downloads` | 下载的图片、视频和导出数据 |
| `.env` | 以环境变量注入 | WebUI Token、身份加密密钥和挂载路径 |

`FETCHSHELF_IDENTITY_KEY` 用于加密采集身份中的 Cookie、代理和设备信息。密钥丢失或更换后，已有密文
无法恢复，因此应单独安全备份。正式环境也可以通过 `FETCHSHELF_IDENTITY_KEY_FILE` 使用 Docker
Secret，文件形式的密钥优先于环境变量。

## 常用操作

查看运行状态：

```bash
docker compose ps
docker compose logs --tail=100
```

持续查看日志：

```bash
docker compose logs -f
```

停止或重新启动：

```bash
docker compose stop
docker compose restart
```

修改代码或配置后重建：

```bash
docker compose up -d --build
```

## 更新与迁移

### 更新当前部署

更新前先备份 `.env`、`SETTINGS_DIR` 和 `DOWNLOADS_DIR`，并确认没有正在写入的采集任务。

```bash
git pull
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

只要持久化目录保持不变，重建容器不会主动删除已下载媒体和配置。更新后应检查：

- WebUI 能否正常登录
- 账号和 Deleted Accounts 数量是否正确
- 定时任务、监控任务及任务历史是否完整
- 下载根目录仍为 `/app/downloads`
- 新任务能否正常启动、暂停和继续

### 从旧容器迁移

迁移已有 Docker 数据时，不要直接删除旧容器或旧目录。建议顺序如下：

1. 记录旧容器的镜像、环境变量和挂载路径
2. 暂停采集任务，等待当前文件写入结束
3. 备份配置目录、下载目录和身份加密密钥；支持快照的存储系统建议同时创建快照
4. 将新 Compose 的 `SETTINGS_DIR`、`DOWNLOADS_DIR` 指向原持久化目录
5. 停止旧容器后再启动新容器
6. 核对账号数量、任务状态、媒体目录和最近作品时间
7. 确认稳定运行后，再决定是否移除旧容器或快照

同一时间不要让新旧两个容器写入同一套配置和下载目录。

如果从改名前的版本升级，还需要注意：

- 将旧 `.env` 中的 WebUI Token 和身份密钥分别写入
  `FETCHSHELF_API_TOKEN`、`FETCHSHELF_IDENTITY_KEY`；旧变量名不会继续生效
- 身份密钥的值必须保持不变，否则已加密的 Cookie、代理和设备信息无法解密
- 新 Compose 的服务名和容器名均为 `fetchshelf`，启动前应先停止占用同一端口的旧容器
- 首次启动会把配置目录中的旧数据库一次性复制为 `FetchShelf.db`，不会修改或删除原数据库

## Cookie、身份与访问安全

- 许多公开账号不配置 Cookie 也可以采集；Cookie 不是所有任务的默认必需项。
- 使用登录 Cookie 可能改善部分内容的可见性，但也会增加登录账号被限流或风控的风险。
- 建议按任务需求决定是否使用 Cookie，不要把“Cookie 失效即暂停”设成所有任务的默认规则。
- `FETCHSHELF_API_TOKEN` 为空时，仅允许 loopback 请求；Docker 或局域网访问通常会返回 `403`。
- 不要把 WebUI 直接暴露到公网。确需远程访问时，应使用 HTTPS、反向代理和额外的访问控制。
- 外部 `encipher.py` 会以应用权限执行，只能使用可信代码。

Cookie 获取方式可参考 [Cookie 获取教程](./docs/Cookie获取教程.md)。

## API 与高级用法

容器启动后可访问：

- WebUI：`http://主机IP:5555/ui`
- Swagger API 文档：`http://主机IP:5555/docs`
- ReDoc：`http://主机IP:5555/redoc`

项目仍保留 `main.py` 和源码终端模式，供调试、接口研究和二次开发使用。但新用户和正式部署应优先
使用 `main_webui.py` 对应的 Docker WebUI。

前端开发说明见 [webui/README.md](./webui/README.md)，完整历史参数说明见
[FetchShelf 文档](./docs/FetchShelf文档.md)。

## 常见问题

### WebUI 显示 403 或 Token 验证失败

确认输入值与容器环境中的 `FETCHSHELF_API_TOKEN` 完全一致。修改 `.env` 后需要重新创建容器：

```bash
docker compose up -d
```

### 文件没有出现在宿主机下载目录

确认 WebUI 设置中的 `root` 为 `/app/downloads`，并检查 `DOWNLOADS_DIR` 是否正确挂载。

### Windows 版本还能使用吗

历史代码和构建工作流仍可能存在，但当前 README 不再推荐可执行文件部署，也不保证它与 WebUI
功能同步。Windows 用户建议安装 Docker Desktop 后按本文运行。

### Linux ARM64 是否支持一键处理头像

Docker 主体可以在常见 ARM64 环境构建，但 Linux ARM64 的 MediaPipe 支持取决于可用依赖。
人脸识别头像处理在 Linux AMD64 上支持更完整；不支持时不影响普通采集和下载。

## 合规与免责声明

本项目仅供学习、研究和处理已获授权的内容。使用者应遵守所在地法律法规、平台规则、隐私要求和
知识产权约束，并对自己的部署、账号、数据采集和文件使用行为承担全部责任。

项目按现状提供，不承诺接口长期有效，也不对第三方平台变化、账号限制、数据损失或使用后果负责。
请勿使用本项目下载、传播未获授权的受版权保护内容，或从事任何违法活动。

使用、修改和分发本项目时还需遵守 [GNU General Public License v3.0](./license)。

## 致谢

本项目由 `TikTokDownloader` 演进而来，感谢原作者
[JoeanAmier](https://github.com/JoeanAmier/TikTokDownloader) 以及所有开源依赖和贡献者。
