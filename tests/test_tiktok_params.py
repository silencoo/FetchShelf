import pytest

from src.encrypt import TikTokParams
from src.tools import is_node_available


@pytest.mark.skipif(not is_node_available(), reason="Node.js 18+ is required")
def test_tiktok_signer_generates_all_current_web_parameters():
    signer = TikTokParams()
    result = signer.sign(
        query="aid=1988&count=2",
        ms_token="test_ms_token_123",
    )

    assert signer.available is True
    assert result["X-Dynosaur"]
    assert result["X-Gnarly"]
    assert result["X-Bogus"]


@pytest.mark.skipif(not is_node_available(), reason="Node.js 18+ is required")
def test_tiktok_signer_builds_complete_query():
    signer = TikTokParams()
    query = signer.sign_url(
        query={"aid": "1988", "count": 2},
        ms_token="test_ms_token_123",
    )

    assert query.startswith("aid=1988&count=2")
    assert "&X-Dynosaur=" in query
    assert "&msToken=test_ms_token_123" in query
    assert "&X-Bogus=" in query
    assert "&X-Gnarly=" in query
    assert query.index("X-Dynosaur=") < query.index("msToken=")
    assert query.index("msToken=") < query.index("X-Bogus=")
