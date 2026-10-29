# Unofficial TikTok API in Python

This is an unofficial api wrapper for TikTok.com in python. With this api you are able to call most trending and fetch specific user information as well as much more.

[![DOI](https://zenodo.org/badge/188710490.svg)](https://zenodo.org/badge/latestdoi/188710490) [![GitHub release (latest by date)](https://img.shields.io/github/v/release/davidteather/TikTok-Api)](https://github.com/davidteather/TikTok-Api/releases) [![GitHub](https://img.shields.io/github/license/davidteather/TikTok-Api)](https://github.com/davidteather/TikTok-Api/blob/main/LICENSE) [![Downloads](https://pepy.tech/badge/tiktokapi)](https://pypi.org/project/TikTokApi/) [![Support Server](https://img.shields.io/discord/783108952111579166.svg?color=7289da&logo=discord&style=flat-square)](https://discord.gg/yyPhbfma6f)

This api is designed to **retrieve data** TikTok. It **can not be used post or upload** content to TikTok on the behalf of a user. It has **no support for any user-authenticated routes**, if you can't access it while being logged out on their website you can't access it here.

## Table of Contents

- [Documentation](#documentation)
- [Getting Started](#getting-started)
  - [Installing](#installing)
  - [Common Issues](#common-issues)
- [Quick Start Guide](#quick-start-guide)
  - [Examples](https://github.com/davidteather/TikTok-Api/tree/main/examples)

## Documentation

You can find the full documentation [here](https://davidteather.github.io/TikTok-Api)

## Getting Started

To get started using this API follow the instructions below.

### Installing

**Note:** Installation requires python3.9+

If you run into an issue please check the closed issues on the github, although feel free to re-open a new issue if you find an issue that's been closed for a few months. The codebase can and does run into similar issues as it has before, because TikTok changes things up.

```sh
pip install TikTokApi
```

`TikTokApi.create_sessions()` now uses `cloakbrowser` by default for Chromium sessions, so the stealth browser binary is downloaded automatically on first launch. If you intentionally switch back to raw Playwright via `browser_engine="playwright"`, run `python -m playwright install`.

#### Docker Installation

Clone this repository onto a local machine (or just the Dockerfile since it installs TikTokApi from pip) then run the following commands.

```sh
docker pull mcr.microsoft.com/playwright:focal
docker build . -t tiktokapi:latest
docker run -v TikTokApi --rm tiktokapi:latest python3 your_script.py
```

**Note** this assumes your script is named your_script.py and lives in the root of this directory.

### Common Issues

- **EmptyResponseException** - this means TikTok is blocking the request and detects you're a bot. This can be a problem with your setup or the library itself
  - you may need a proxy to successfully scrape TikTok. In practice, residential proxies often work better than datacenter proxies.

- **Browser Has no Attribute** - if you're using the default `cloakbrowser` launcher, make sure `cloakbrowser` is installed and the first launch can download its Chromium binary. If you explicitly set `browser_engine="playwright"`, run `python3 -m playwright install`. If your error persists try the [playwright-python](https://github.com/microsoft/playwright-python) quickstart guide and diagnose issues from there.

- **API methods returning Coroutine** - many of the API's methods are async so make sure your program awaits them for proper functionality

## Quick Start Guide

Here's a quick bit of code to get the most recent trending videos on TikTok. There's more examples in the [examples](https://github.com/davidteather/TikTok-Api/tree/main/examples) directory.

```py
from TikTokApi import TikTokApi
import asyncio
import os

ms_token = os.environ.get("ms_token", None) # get your own ms_token from your cookies on tiktok.com

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

To directly run the example scripts from the repository root, use the `-m` option on python.

```sh
python -m examples.trending_example
```

You can access the full data dictionary the object was created from with `.as_dict`. On a video this may look like
[this](https://gist.github.com/davidteather/7c30780bbc30772ba11ec9e0b909e99d). TikTok changes their structure from time to time so it's worth investigating the structure of the dictionary when you use this package.
