from types import SimpleNamespace

import pytest

from src.application.main_server import APIServer


def _scheduled_task(**overrides):
    task = {
        "task_id": "T000123",
        "schedule_name": "每日抖音下载",
        "schedule_platform": "douyin",
        "schedule_bark_url": "https://api.day.app/example",
        "status": "success",
        "payload": {"proxy": ""},
        "result": {
            "message": "账号批量下载任务完成！",
            "data": {
                "queued": 3,
                "success": 3,
                "failed": 0,
                "skipped": 0,
                "failures": [],
            },
        },
    }
    task.update(overrides)
    return task


def test_build_ui_task_completion_notification_reports_success_counts():
    title, body = APIServer._build_ui_task_completion_notification(_scheduled_task())

    assert title == "下载完成: 每日抖音下载"
    assert "抖音" in body
    assert "任务 T000123" in body
    assert "成功 3" in body
    assert "失败 0" in body


def test_build_ui_task_completion_notification_surfaces_403_failure():
    task = _scheduled_task(
        status="failed",
        result={
            "message": "账号批量下载任务失败！",
            "data": {
                "queued": 2,
                "success": 0,
                "failed": 2,
                "skipped": 0,
                "failures": [
                    {
                        "reason": "HTTP 403 Forbidden（Cookie 或采集身份可能已失效）",
                    }
                ],
            },
        },
    )

    title, body = APIServer._build_ui_task_completion_notification(task)

    assert title == "下载失败: 每日抖音下载"
    assert "失败 2" in body
    assert "HTTP 403 Forbidden" in body
    assert "Cookie 或采集身份可能已失效" in body


def test_partial_batch_is_not_reported_as_full_success():
    result = {
        "message": "账号批量下载任务完成：成功 2，失败 1",
        "data": {"queued": 3, "success": 2, "failed": 1, "skipped": 0},
    }
    task = _scheduled_task(status="partial_success", result=result)

    assert APIServer._ui_task_result_status(result) == "partial_success"
    title, body = APIServer._build_ui_task_completion_notification(task)
    assert title == "下载部分失败: 每日抖音下载"
    assert "成功 2" in body
    assert "失败 1" in body


def test_failure_category_distinguishes_actionable_causes():
    assert APIServer._account_failure_category("HTTP 403 Forbidden") == "identity"
    assert APIServer._account_failure_category("账号已注销") == "account_unavailable"
    assert APIServer._account_failure_category("proxy timeout") == "network"
    assert APIServer._account_failure_category("保存文件失败") == "download"
    assert APIServer._account_failure_category("解析响应失败") == "parse"


def test_account_request_failure_reason_recognizes_http_status():
    forbidden = SimpleNamespace(response=SimpleNamespace(status_code=403))
    unavailable = SimpleNamespace(response=SimpleNamespace(status_code=503))

    assert "403 Forbidden" in APIServer._account_request_failure_reason(forbidden)
    assert "HTTP 503" in APIServer._account_request_failure_reason(unavailable)
    assert APIServer._account_request_failure_reason(None) == "账号作品下载失败"


@pytest.mark.asyncio
async def test_notify_ui_task_completion_sends_and_records_delivery():
    server = APIServer.__new__(APIServer)
    server.task_journal = None
    server.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    calls = []

    async def fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return True, ""

    server._send_bark_notification = fake_send
    task = _scheduled_task()

    await server._notify_ui_task_completion(task)

    assert len(calls) == 1
    assert calls[0][1]["title"] == "下载完成: 每日抖音下载"
    assert task["schedule_notification"]["status"] == "sent"


@pytest.mark.asyncio
async def test_execute_ui_task_dispatches_terminal_schedule_notification():
    server = APIServer.__new__(APIServer)
    server.task_journal = None
    task = _scheduled_task(
        endpoint="/workflow/douyin/account_batch",
        status="pending",
        result=None,
        started_at=None,
        finished_at=None,
        updated_at="",
        message="",
        error="",
        pause_supported=False,
    )
    server.ui_tasks = {task["task_id"]: task}
    notifications = []

    async def fake_endpoint(endpoint, payload):
        return {
            "message": "账号批量下载任务完成！",
            "data": {"queued": 1, "success": 1, "failed": 0, "skipped": 0},
        }

    async def fake_notify(completed_task):
        notifications.append(completed_task["status"])

    server._execute_ui_endpoint = fake_endpoint
    server._notify_ui_task_completion = fake_notify

    await server._execute_ui_task(task["task_id"], worker_id=1)

    assert task["status"] == "success"
    assert notifications == ["success"]
