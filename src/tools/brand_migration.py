from shutil import copy2

from ..custom import PROJECT_ROOT


class BrandMigration:
    LEGACY_DB_FILES = (
        PROJECT_ROOT.joinpath("DouK-Downloader.db"),
        PROJECT_ROOT.joinpath("TikTokDownloader.db"),
    )
    NEW_DB_FILE = PROJECT_ROOT.joinpath("FetchShelf.db")

    @classmethod
    def migrate_database(cls) -> None:
        if cls.NEW_DB_FILE.exists():
            return
        for legacy_file in cls.LEGACY_DB_FILES:
            if legacy_file.exists():
                temporary_file = cls.NEW_DB_FILE.with_name(
                    f".{cls.NEW_DB_FILE.name}.migrating"
                )
                copy2(legacy_file.resolve(), temporary_file.resolve())
                temporary_file.replace(cls.NEW_DB_FILE)
                return
