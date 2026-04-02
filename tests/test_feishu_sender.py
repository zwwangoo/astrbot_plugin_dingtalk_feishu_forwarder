"""FeishuSender 单元测试"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import FeishuMessage, TokenCache
from senders.feishu_sender import FeishuSender, MAX_RETRIES


@pytest.fixture
def sender():
    return FeishuSender(app_id="test_app_id", app_secret="test_app_secret")


@pytest.fixture
def sample_message():
    return FeishuMessage(
        msg_type="text",
        content={"text": "hello"},
        forward_tag="[FWD]",
    )


def _mock_response(code=0, msg="success", token=None, expire=7200):
    """创建模拟的 aiohttp 响应"""
    resp = AsyncMock()
    data = {"code": code, "msg": msg}
    if token:
        data["tenant_access_token"] = token
        data["expire"] = expire
    resp.json = AsyncMock(return_value=data)
    return resp


class TestRefreshToken:
    """测试 _refresh_token 方法"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, sender):
        mock_resp = _mock_response(code=0, token="new_token", expire=7200)
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp), __aexit__=AsyncMock()))

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            token = await sender._refresh_token()

        assert token == "new_token"
        assert sender._token_cache is not None
        assert sender._token_cache.token == "new_token"
        assert not sender._token_cache.is_expired

    @pytest.mark.asyncio
    async def test_refresh_token_failure_raises(self, sender):
        mock_resp = _mock_response(code=10003, msg="invalid app_id")

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_cm)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session_cm):
            with pytest.raises(RuntimeError, match="获取飞书 tenant_access_token 失败"):
                await sender._refresh_token()


class TestGetValidToken:
    """测试 _get_valid_token 方法"""

    @pytest.mark.asyncio
    async def test_returns_cached_token_when_valid(self, sender):
        sender._token_cache = TokenCache(token="cached_token", expires_at=time.time() + 3600)
        token = await sender._get_valid_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_refreshes_when_expired(self, sender):
        sender._token_cache = TokenCache(token="old_token", expires_at=time.time() - 10)

        mock_resp = _mock_response(code=0, token="fresh_token", expire=7200)
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp), __aexit__=AsyncMock()))

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            token = await sender._get_valid_token()

        assert token == "fresh_token"

    @pytest.mark.asyncio
    async def test_refreshes_when_no_cache(self, sender):
        mock_resp = _mock_response(code=0, token="new_token", expire=7200)
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp), __aexit__=AsyncMock()))

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            token = await sender._get_valid_token()

        assert token == "new_token"


class TestSend:
    """测试 send 方法"""

    @pytest.mark.asyncio
    async def test_send_success(self, sender, sample_message):
        # Mock token
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)

        mock_resp = _mock_response(code=0)
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp), __aexit__=AsyncMock()))

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            result = await sender.send(sample_message, "chat_123")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_api_error_retries_and_fails(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)

        mock_resp = _mock_response(code=10001, msg="some error")
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp), __aexit__=AsyncMock()))

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await sender.send(sample_message, "chat_123")

        assert result is False
        # Should have retried MAX_RETRIES times
        assert mock_sleep.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_send_network_error_retries(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)

        import aiohttp as aiohttp_mod
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=aiohttp_mod.ClientError("connection failed"))

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await sender.send(sample_message, "chat_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_token_expired_auto_refresh(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)

        # First call returns token expired, second returns success
        expired_resp = _mock_response(code=99991663, msg="token expired")
        success_resp = _mock_response(code=0)
        token_resp = _mock_response(code=0, token="refreshed_token", expire=7200)

        call_count = 0

        def mock_post_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First send attempt - token expired
                return AsyncMock(__aenter__=AsyncMock(return_value=expired_resp), __aexit__=AsyncMock())
            elif call_count == 2:
                # Token refresh call
                return AsyncMock(__aenter__=AsyncMock(return_value=token_resp), __aexit__=AsyncMock())
            else:
                # Second send attempt - success
                return AsyncMock(__aenter__=AsyncMock(return_value=success_resp), __aexit__=AsyncMock())

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=mock_post_side_effect)

        with patch("aiohttp.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await sender.send(sample_message, "chat_123")

        assert result is True
