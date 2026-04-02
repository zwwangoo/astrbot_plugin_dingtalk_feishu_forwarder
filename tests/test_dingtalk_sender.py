"""DingTalkSender 单元测试"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import DingTalkMessage, TokenCache
from senders.dingtalk_sender import DingTalkSender, MAX_RETRIES


@pytest.fixture
def sender():
    return DingTalkSender(app_key="test_app_key", app_secret="test_app_secret")


@pytest.fixture
def sample_message():
    return DingTalkMessage(
        msg_type="text",
        content={"content": "hello"},
        forward_tag="[FWD]",
    )


def _mock_response(errcode=0, errmsg="ok", token=None, expires_in=7200):
    """创建模拟的 aiohttp 响应"""
    resp = AsyncMock()
    data = {"errcode": errcode, "errmsg": errmsg}
    if token:
        data["access_token"] = token
        data["expires_in"] = expires_in
    resp.json = AsyncMock(return_value=data)
    return resp


def _mock_session(post_return=None, post_side_effect=None, get_return=None):
    """创建模拟的 aiohttp session"""
    mock_session = AsyncMock()
    if post_side_effect:
        mock_session.post = MagicMock(side_effect=post_side_effect)
    elif post_return:
        mock_session.post = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=post_return),
                __aexit__=AsyncMock(return_value=False),
            )
        )
    if get_return:
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=get_return),
                __aexit__=AsyncMock(return_value=False),
            )
        )
    return mock_session


def _patch_session(mock_session):
    return patch(
        "aiohttp.ClientSession",
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=False),
        ),
    )


class TestRefreshToken:
    """测试 _refresh_token 方法"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, sender):
        mock_resp = _mock_response(errcode=0, token="new_token", expires_in=7200)
        session = _mock_session(get_return=mock_resp)

        with _patch_session(session):
            token = await sender._refresh_token()

        assert token == "new_token"
        assert sender._token_cache is not None
        assert sender._token_cache.token == "new_token"
        assert not sender._token_cache.is_expired

    @pytest.mark.asyncio
    async def test_refresh_token_failure_raises(self, sender):
        mock_resp = _mock_response(errcode=40089, errmsg="invalid appkey")
        session = _mock_session(get_return=mock_resp)

        with _patch_session(session):
            with pytest.raises(RuntimeError, match="获取钉钉 access_token 失败"):
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
        mock_resp = _mock_response(errcode=0, token="fresh_token", expires_in=7200)
        session = _mock_session(get_return=mock_resp)

        with _patch_session(session):
            token = await sender._get_valid_token()

        assert token == "fresh_token"

    @pytest.mark.asyncio
    async def test_refreshes_when_no_cache(self, sender):
        mock_resp = _mock_response(errcode=0, token="new_token", expires_in=7200)
        session = _mock_session(get_return=mock_resp)

        with _patch_session(session):
            token = await sender._get_valid_token()

        assert token == "new_token"


class TestSend:
    """测试 send 方法"""

    @pytest.mark.asyncio
    async def test_send_success(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)
        mock_resp = _mock_response(errcode=0)
        session = _mock_session(post_return=mock_resp)

        with _patch_session(session):
            result = await sender.send(sample_message, "chat_123")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_api_error_retries_and_fails(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)
        mock_resp = _mock_response(errcode=10001, errmsg="some error")
        session = _mock_session(post_return=mock_resp)

        with _patch_session(session):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await sender.send(sample_message, "chat_123")

        assert result is False
        assert mock_sleep.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_send_network_error_retries(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)

        import aiohttp as aiohttp_mod
        session = AsyncMock()
        session.post = MagicMock(side_effect=aiohttp_mod.ClientError("connection failed"))

        with _patch_session(session):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await sender.send(sample_message, "chat_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_token_expired_auto_refresh(self, sender, sample_message):
        sender._token_cache = TokenCache(token="valid_token", expires_at=time.time() + 3600)

        expired_resp = _mock_response(errcode=40014, errmsg="token expired")
        success_resp = _mock_response(errcode=0)
        token_resp = _mock_response(errcode=0, token="refreshed_token", expires_in=7200)

        call_count = {"post": 0, "get": 0}

        def mock_post_side_effect(*args, **kwargs):
            call_count["post"] += 1
            if call_count["post"] == 1:
                return AsyncMock(__aenter__=AsyncMock(return_value=expired_resp), __aexit__=AsyncMock())
            return AsyncMock(__aenter__=AsyncMock(return_value=success_resp), __aexit__=AsyncMock())

        session = AsyncMock()
        session.post = MagicMock(side_effect=mock_post_side_effect)
        session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=token_resp),
                __aexit__=AsyncMock(),
            )
        )

        with _patch_session(session):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await sender.send(sample_message, "chat_123")

        assert result is True
