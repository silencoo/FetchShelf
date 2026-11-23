from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.main_server import APIServer
from src.webui.task_journal import TaskJournal


def test_account_activity_filters_and_checkpoint_details(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "fixture-token")
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.setup_routes()
    client = TestClient(server.server)
    headers = {"token": "fixture-token"}
    path = "/ui/api/accounts/activity"
    names = ("old", "empty", "private", "no-updates", "failed", "legacy", "never")
    urls = {name: f"https://example.test/{name}" for name in names}
    configured = [{"url": url, "mark": name} for name, url in urls.items()]
    server._active_account_rows = lambda source: (
        [*configured, configured[0]] if source == "douyin"
        else [{"url": urls["old"], "mark": "Separate TikTok account"}]
    )
    server.collector_store = SimpleNamespace(
        get_identity=lambda identity_id: SimpleNamespace(name="Fixture collector"),
    )
    assert client.get(path).status_code == 403

    with TaskJournal(tmp_path / "tasks.sqlite3") as journal:
        server.task_journal = journal
        journal.save_task({
            "task_id": "T000001", "endpoint": "/workflow/douyin/account_batch",
            "status": "running",
        })
        journal.prepare_accounts("T000001", [{"url": urls["private"]}])
        rows = [
            ("old", "success", "success", "2020-05-01T00:00:00+09:00"),
            ("empty", "skipped", "no_works", ""),
            ("private", "failed", "private_not_visible", "2021-05-01T00:00:00Z"),
            ("no-updates", "success", "no_matching_items", ""),
            ("failed", "failed", "timeout", ""),
            ("legacy", "success", "", ""),
        ]
        for name, status, code, date in rows:
            journal.save_account_activity(
                platform="douyin", url=urls[name], status=status,
                outcome_code=code, latest_seen_work_at=date,
            )
            if name == "private":
                journal.mark_account_finished(
                    "T000001", 1, identity_id="collector-a",
                    status=status, reason="Current identity cannot see the posts",
                    result={"outcome_code": code},
                )

        def page(**params):
            response = client.get(path, headers=headers, params=params)
            assert response.status_code == 200, response.text
            return response.json()

        assert page()["total"] == 8
        assert page(platform="tiktok")["items"][0]["status"] == "never"
        assert {row["mark"] for row in page(status="never")["items"]} == {"never", "Separate TikTok account"}
        assert [row["mark"] for row in page(status="empty")["items"]] == ["empty"]
        assert [row["mark"] for row in page(status="failed")["items"]] == ["failed"]
        assert {row["status"] for row in page(status="success")["items"]} == {
            "success", "no_updates", "legacy_success",
        }
        assert [row["mark"] for row in page(age_days=365, sort="latest_asc")["items"]] == ["old", "private"]
        match = page(search="PRIVATE", status="visibility")["items"][0]
        assert match["latest_work_at"] == "2021-05-01T00:00:00Z"
        assert page(page=99, page_size=3)["page"] == 3

        details_path = f"{path}/details"
        params = {"platform": "douyin", "url": urls["private"]}
        assert client.get(details_path, params=params).status_code == 403
        details = client.get(details_path, headers=headers, params=params).json()
        assert details["identity"] == "Fixture collector"
        assert details["task_id"] == "T000001"
        assert details["reason"] == "Current identity cannot see the posts"
        details = client.get(details_path, headers=headers, params={
            "platform": "douyin", "url": urls["failed"],
        }).json()
        assert details["identity"] == ""
        assert details["status"] == "failed"
