import pytest

from src.config.parameter import Parameter
from src.config.settings import Settings
from src.custom import function
from src.models.settings import Settings as SettingsModel


def test_request_delay_defaults_to_safer_six_seconds():
    assert Settings.default["request_delay"] == 6.0
    assert SettingsModel().request_delay is None


def test_get_wait_time_uses_log_normal_sample(monkeypatch):
    monkeypatch.setattr(function, "lognormvariate", lambda mu, sigma: 3.25)

    assert function.get_wait_time(avg_delay=6.0) == 3.25
    assert function.get_wait_time(avg_delay=0) == 0.0


@pytest.mark.asyncio
async def test_wait_can_be_disabled(monkeypatch):
    calls = []

    async def fake_sleep(delay):
        calls.append(delay)

    previous = function._REQUEST_DELAY_MEAN
    monkeypatch.setattr(function, "sleep", fake_sleep)
    try:
        function.configure_wait(0)
        await function.wait()
    finally:
        function.configure_wait(previous)

    assert calls == []


@pytest.mark.asyncio
async def test_wait_sleeps_once_with_sampled_delay(monkeypatch):
    calls = []

    async def fake_sleep(delay):
        calls.append(delay)

    previous = function._REQUEST_DELAY_MEAN
    monkeypatch.setattr(function, "sleep", fake_sleep)
    monkeypatch.setattr(function, "get_wait_time", lambda: 2.75)
    try:
        await function.wait()
    finally:
        function.configure_wait(previous)

    assert calls == [2.75]


def test_parameter_runtime_delay_update_reconfigures_wait():
    parameter = Parameter.__new__(Parameter)
    parameter.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
        },
    )()
    previous = function._REQUEST_DELAY_MEAN
    try:
        value = parameter._Parameter__set_request_delay(2.5)
        assert value == 2.5
        assert function._REQUEST_DELAY_MEAN == 2.5
    finally:
        function.configure_wait(previous)
