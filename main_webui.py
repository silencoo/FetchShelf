from asyncio import CancelledError, run

from src.application import TikTokDownloader


async def main():
    async with TikTokDownloader() as downloader:
        try:
            downloader.check_config()
            await downloader.check_settings(False)
            await downloader.webui()
        except (
            KeyboardInterrupt,
            CancelledError,
        ):
            return


if __name__ == "__main__":
    run(main())
