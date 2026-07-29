from pathlib import Path

import pytest

from src.tools.brand_migration import BrandMigration


@pytest.mark.parametrize(
    "legacy_name",
    ("DouK-Downloader.db", "TikTokDownloader.db"),
)
def test_brand_migration_copies_legacy_database_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_name: str,
):
    legacy_file = tmp_path / legacy_name
    target_file = tmp_path / "FetchShelf.db"
    legacy_file.write_bytes(b"legacy-database")
    monkeypatch.setattr(
        BrandMigration,
        "LEGACY_DB_FILES",
        (legacy_file,),
    )
    monkeypatch.setattr(BrandMigration, "NEW_DB_FILE", target_file)

    BrandMigration.migrate_database()

    assert target_file.read_bytes() == b"legacy-database"
    assert legacy_file.read_bytes() == b"legacy-database"
    assert not (tmp_path / ".FetchShelf.db.migrating").exists()

    target_file.write_bytes(b"current-database")
    BrandMigration.migrate_database()
    assert target_file.read_bytes() == b"current-database"
