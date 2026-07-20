from src.application.main_server import APIServer
from src.config.parameter import Parameter


def test_webui_account_normalization_parses_string_booleans():
    rows = APIServer._normalize_account_items(
        [
            {
                "mark": "A",
                "url": "https://www.douyin.com/user/example",
                "enable": "false",
                "auto_update_earliest": "1",
            }
        ]
    )

    assert rows[0]["enable"] is False
    assert rows[0]["auto_update_earliest"] is True


def test_parameter_account_rows_parse_string_booleans():
    rows = Parameter.check_urls_params(
        [
            {
                "mark": "A",
                "url": "https://www.tiktok.com/@example",
                "enable": "0",
                "auto_update_earliest": "enabled",
            }
        ]
    )

    assert rows[0].enable is False
    assert rows[0].auto_update_earliest is True


def test_parameter_general_bool_checks_parse_strings():
    assert Parameter.check_bool_true("false") is False
    assert Parameter.check_bool_false("true") is True


def test_schedule_normalization_parses_string_booleans():
    server = APIServer.__new__(APIServer)
    schedule = APIServer._normalize_schedule_payload(
        server,
        {
            "name": "Nightly",
            "platform": "douyin",
            "enabled": "off",
            "use_settings": "false",
            "items": [
                {
                    "url": "https://www.douyin.com/user/example",
                    "enable": "yes",
                }
            ],
        },
    )

    assert schedule["enabled"] is False
    assert schedule["use_settings"] is False
    assert schedule["items"][0]["enable"] is True
