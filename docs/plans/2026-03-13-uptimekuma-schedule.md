# Uptime Kuma Push For Account Batch Schedules Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-schedule Uptime Kuma push notifications that fire when account-batch schedules finish (automatic or manual).

**Architecture:** Store an optional `uptime_kuma_url` on account-batch schedules, attach schedule metadata to the UI task when enqueued, and send a non-blocking GET to the Kuma URL from `_execute_ui_task` after task completion. Build the push URL via a small helper for testability and append `status` and `msg` query parameters.

**Tech Stack:** Python (FastAPI + httpx), Web UI static HTML/JS, pytest.

---

### Task 1: Add helper to build Kuma push URL (test-first)

**Files:**
- Create: `tests/test_uptime_kuma.py`
- Modify: `src/application/main_server.py`

**Step 1: Write the failing test**

```python
from urllib.parse import urlparse, parse_qs

from src.application.main_server import APIServer


def test_build_uptime_kuma_url_appends_status_and_msg():
    base = "https://kuma.example/push/abc?foo=bar"
    url = APIServer._build_uptime_kuma_url(base, "up", "hello world")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "kuma.example"
    assert qs["foo"] == ["bar"]
    assert qs["status"] == ["up"]
    assert qs["msg"] == ["hello world"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_uptime_kuma.py::test_build_uptime_kuma_url_appends_status_and_msg -v`
Expected: FAIL with `AttributeError` or missing function.

**Step 3: Write minimal implementation**

Add helper in `src/application/main_server.py`:

```python
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

    @staticmethod
    def _build_uptime_kuma_url(base_url: str, status: str, message: str) -> str:
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["status"] = status
        if message:
            query["msg"] = message
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_uptime_kuma.py::test_build_uptime_kuma_url_appends_status_and_msg -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_uptime_kuma.py src/application/main_server.py
git commit -m "test: add uptime kuma url builder"
```

---

### Task 2: Add schedule field plumbing (validation + normalization + UI)

**Files:**
- Modify: `src/application/main_server.py`
- Modify: `src/webui/static/index.html`
- Modify: `src/webui/static/app.js`

**Step 1: Write failing test**

Extend `tests/test_uptime_kuma.py`:

```python

def test_schedule_normalizes_uptime_kuma_url():
    payload = {
        "platform": "douyin",
        "hour": 1,
        "minute": 2,
        "uptime_kuma_url": "https://kuma/push/abc",
    }
    server = APIServer.__new__(APIServer)
    server._now_text = lambda: "2026-03-13 00:00:00"
    normalized = APIServer._normalize_schedule_payload(server, payload)
    assert normalized["uptime_kuma_url"] == "https://kuma/push/abc"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_uptime_kuma.py::test_schedule_normalizes_uptime_kuma_url -v`
Expected: FAIL (missing field).

**Step 3: Implement validation + normalization**

Update `src/application/main_server.py`:
- `_validate_ui_schedule_payload` to accept `uptime_kuma_url` as `str` or `None`.
- `_normalize_schedule_payload` to store `uptime_kuma_url` (normalized string).

**Step 4: Update Web UI form**

Update `src/webui/static/index.html` and `src/webui/static/app.js`:
- Add input labeled `Uptime Kuma Push URL（可选）` in the schedule form.
- Include `uptime_kuma_url` in `schedulePayloadFromForm()`.

**Step 5: Run tests**

Run: `pytest tests/test_uptime_kuma.py::test_schedule_normalizes_uptime_kuma_url -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add src/application/main_server.py src/webui/static/index.html src/webui/static/app.js tests/test_uptime_kuma.py
git commit -m "feat: add uptime kuma url to schedules"
```

---

### Task 3: Attach schedule metadata to UI tasks and send push on completion

**Files:**
- Modify: `src/application/main_server.py`

**Step 1: Write failing test**

Extend `tests/test_uptime_kuma.py` with a small unit test for status decision:

```python

def test_uptime_kuma_status_down_when_failed_counts():
    task = {
        "status": "success",
        "result": {"data": {"failed": 1, "queued": 2}},
    }
    server = APIServer.__new__(APIServer)
    status, msg = APIServer._build_uptime_kuma_status(server, task, "Task", "douyin")
    assert status == "down"
    assert "failed" in msg
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_uptime_kuma.py::test_uptime_kuma_status_down_when_failed_counts -v`
Expected: FAIL (missing helper).

**Step 3: Implement metadata attach + push logic**

In `src/application/main_server.py`:
- When enqueuing from schedules (both `_ui_schedule_runner` and `webui_run_schedule_now`), attach:
  - `task["schedule_id"]`, `task["schedule_name"]`, `task["schedule_platform"]`, `task["schedule_uptime_kuma_url"]`.
- Add helper `_build_uptime_kuma_status(task, name, platform) -> tuple[str, str]` that:
  - Returns `("down", msg)` if task status is `failed`, or `result.data.failed > 0`, or `result.data.queued == 0`.
  - Otherwise `("up", msg)`.
  - `msg` includes name, platform, result summary counts.
- In `_execute_ui_task` after task completion:
  - If `schedule_uptime_kuma_url` exists, build URL with `_build_uptime_kuma_url`.
  - Use `create_client` with proxy/timeout to GET the URL.
  - Log exceptions and continue.

**Step 4: Run tests**

Run: `pytest tests/test_uptime_kuma.py::test_uptime_kuma_status_down_when_failed_counts -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/application/main_server.py tests/test_uptime_kuma.py
git commit -m "feat: send uptime kuma push for schedule tasks"
```

---

### Task 4: Full test run

**Files:**
- None

**Step 1: Run full test suite**

Run: `pytest`
Expected: PASS (same or more tests).

**Step 2: Commit (if needed)**

If any fixes were made during testing:

```bash
git add -A
git commit -m "fix: stabilize uptime kuma push implementation"
```
