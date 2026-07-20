import asyncio

import pytest

from src.manager.database import Database


@pytest.mark.asyncio
async def test_database_reads_use_independent_cursors(tmp_path):
    database = Database()
    database.file = tmp_path / "collector-concurrency.db"

    async with database:
        await asyncio.gather(
            *(
                database.update_mapping_data(
                    f"media-{index}",
                    f"name-{index}",
                    f"mark-{index}",
                )
                for index in range(10)
            )
        )
        rows = await asyncio.gather(
            *(database.read_mapping_data(f"media-{index}") for index in range(10))
        )

    assert [row["NAME"] for row in rows] == [
        f"name-{index}" for index in range(10)
    ]
