# 非官方 TikTok Python API

这是一个针对 TikTok.com 的非官方 Python API 封装。使用此 API，你可以获取热门内容、抓取特定用户信息等更多数据。

[![DOI](https://zenodo.org/badge/188710490.svg)](https://zenodo.org/badge/latestdoi/188710490) [![GitHub release (latest by date)](https://img.shields.io/github/v/release/davidteather/TikTok-Api)](https://github.com/davidteather/TikTok-Api/releases) [![GitHub](https://img.shields.io/github/license/davidteather/TikTok-Api)](https://github.com/davidteather/TikTok-Api/blob/main/LICENSE) [![Downloads](https://pepy.tech/badge/tiktokapi)](https://pypi.org/project/TikTokApi/) [![Support Server](https://img.shields.io/discord/783108952111579166.svg?color=7289da&logo=discord&style=flat-square)](https://discord.gg/yyPhbfma6f)

本 API 旨在从 TikTok 上“获取数据”。它不能用于代表用户在 TikTok 上“发布或上传”内容。它不支持任何需要用户身份验证的路由；如果你无法在“未登录状态”下通过浏览器完成的操作，这个库也无法完成。

## 目录

- [文档](#documentation)
- [快速开始](#getting-started)
  - [安装](#installing)
  - [常见问题](#common-issues)
- [快速上手示例](#quick-start-guide)
  - [示例代码库](https://github.com/davidteather/TikTok-Api/tree/main/examples)

<a name="documentation"></a>
## 文档

完整文档见：[文档站点](https://davidteather.github.io/TikTok-Api)

本地补充说明见：[`INTEGRATION_GUIDE.zh-CN.md`](./INTEGRATION_GUIDE.zh-CN.md)

<a name="getting-started"></a>
## 快速开始

按照以下步骤开始使用本 API。

<a name="installing"></a>
### 安装

注意：需要 Python 3.9 及以上版本

如果遇到问题，请先查看仓库里的已关闭 issue；如果你发现久远的 issue 与现在的问题相同，也可以新开一个 issue。该代码库会受到 TikTok 更新的影响，有时需要一些时间来适配。

```sh
pip install TikTokApi
```

`TikTokApi.create_sessions()` 现在默认对 Chromium 会使用 `cloakbrowser`，首次启动时会自动下载其浏览器二进制。如果你显式切回 `browser_engine="playwright"`，请再执行 `python -m playwright install`。

#### Docker 安装

将本仓库克隆到本地（或只拷贝 Dockerfile，因为它会从 pip 安装 TikTokApi），然后运行以下命令：

```sh
docker pull mcr.microsoft.com/playwright:focal
docker build . -t tiktokapi:latest
docker run -v TikTokApi --rm tiktokapi:latest python3 your_script.py
```

注意：以上示例假设你的脚本名为 your_script.py，且位于仓库根目录。

<a name="common-issues"></a>
### 常见问题

- 空响应异常（EmptyResponseException）——表示 TikTok 拦截了请求并检测到你是机器人。这可能来自你的环境设置或库本身
  - 你可能需要代理才能稳定抓取 TikTok。实践中，住宅代理通常比数据中心代理更稳定。

- “Browser has no attribute …”——如果你使用默认的 `cloakbrowser` 启动方式，请确认已安装 `cloakbrowser`，并且首次启动时可以正常下载浏览器二进制。如果你显式设置了 `browser_engine="playwright"`，请执行 `python3 -m playwright install`。若问题仍在，请参考 [playwright-python](https://github.com/microsoft/playwright-python) 的快速上手指南

- “API 方法返回协程（Coroutine）”——库中很多方法是异步的，请确保在你的程序中使用 `await` 正确调用

<a name="quick-start-guide"></a>
## 快速上手示例

下面是一个示例，用于获取 TikTok 上最新的热门视频。更多示例见 [examples](https://github.com/davidteather/TikTok-Api/tree/main/examples) 目录。

```py
from TikTokApi import TikTokApi
import asyncio
import os

ms_token = os.environ.get("ms_token", None) # 从 tiktok.com 的浏览器 Cookie 中获取你的 ms_token

async def trending_videos():
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            browser_engine=os.getenv("TIKTOK_BROWSER_ENGINE", "cloakbrowser"),
        )
        async for video in api.trending.videos(count=30):
            print(video)
            print(video.as_dict)

if __name__ == "__main__":
    asyncio.run(trending_videos())
```

在仓库根目录下，使用 `-m` 方式可直接运行示例脚本：

```sh
python -m examples.trending_example
```

你可以通过 `.as_dict` 访问对象创建时的完整数据字典。对于视频对象，可能类似于[这个示例](https://gist.github.com/davidteather/7c30780bbc30772ba11ec9e0b909e99d)。由于 TikTok 会不定期调整数据结构，建议在使用时先了解字典结构。
