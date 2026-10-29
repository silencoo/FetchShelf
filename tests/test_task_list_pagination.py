from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.main_server import APIServer
from src.webui_security import REDACTED_VALUE


@pytest.mark.parametrize('status,expected_id', [('', 'T000003'), ('pending', 'T000001')])
def test_task_list_only_redacts_requested_page_and_preserves_global_counts(
    tmp_path, monkeypatch, status, expected_id
):
    monkeypatch.setenv('FETCHSHELF_API_TOKEN', 'pagination-test-token')
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = SimpleNamespace(root=tmp_path)
    server.ui_tasks = {
        f'T{i:06d}': {
            'task_id': f'T{i:06d}', 'status': state,
            'payload': {'cookie': 'fixture-cookie'}, '_internal': 'private-state',
        }
        for i, state in enumerate(('pending', 'running', 'completed'), 1)
    }
    inspected = []
    original = server._public_ui_task

    def render(task):
        inspected.append(task['task_id'])
        return original(task)

    server._public_ui_task = render
    server.setup_routes()
    response = TestClient(server.server).get(
        '/ui/api/tasks', params={'limit': 1, 'status': status},
        headers={'token': 'pagination-test-token'},
    )
    assert response.status_code == 200
    body = response.json()
    assert inspected == [expected_id]
    assert body['items'] == [{
        'task_id': expected_id,
        'status': server.ui_tasks[expected_id]['status'],
        'payload': {'cookie': REDACTED_VALUE},
    }]
    assert (body['count'], body['pending'], body['running'], body['paused']) == (1, 1, 1, 0)
    assert server.ui_tasks[expected_id]['payload']['cookie'] == 'fixture-cookie'
