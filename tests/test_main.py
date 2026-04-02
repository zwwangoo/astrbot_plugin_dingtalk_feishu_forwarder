"""插件主类 DingTalkFeishuForwarder 单元测试"""

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# Stub the astrbot module before importing main
astrbot_star = SimpleNamespace(
    Context=type("Context", (), {}),
    Star=type("Star", (), {"__init__": lambda self, ctx: None}),
    register=lambda *a, **kw: (lambda cls: cls),
)
sys.modules.setdefault("astrbot", SimpleNamespace(api=SimpleNamespace(star=astrbot_star)))
sys.modules.setdefault("astrbot.api", SimpleNamespace(star=astrbot_star))
sys.modules.setdefault("astrbot.api.star", astrbot_star)

from main import DingTalkFeishuForwarder  # noqa: E402
from models import ContentElement, ForwardingDirection, MessageType, ParsedMessage  # noqa: E402


def _make_context(overrides: dict | None = None) -> SimpleNamespace:
    """创建带有效配置的 mock Context。"""
    cfg = {
        "dingtalk_app_key": "dk_key",
        "dingtalk_app_secret": "dk_secret",
        "feishu_app_id": "fs_id",
        "feishu_app_secret": "fs_secret",
        "forwarding_rules": [
            {
                "direction": "dingtalk_to_feishu",
                "source_id": "dt_group_1",
                "target_id": "fs_chat_1",
            },
            {
                "direction": "feishu_to_dingtalk",
                "source_id": "fs_chat_1",
                "target_id": "dt_group_1",
            },
        ],
    }
    if overrides:
        cfg.update(overrides)
    return SimpleNamespace(config=cfg)


def _make_plugin(overrides: dict | None = None) -> DingTalkFeishuForwarder:
    ctx = _make_context(overrides)
    return DingTalkFeishuForwarder(ctx)


# ---------------------------------------------------------------------------
# 初始化测试
# ---------------------------------------------------------------------------

class TestInit:
    def test_valid_config_initializes(self):
        plugin = _make_plugin()
        assert plugin.config is not None
        assert plugin.stats is not None
        assert plugin.loop_detection is not None

    def test_missing_credentials_raises(self):
        with pytest.raises(ValueError, match="配置验证失败"):
            _make_plugin(overrides={"dingtalk_app_key": ""})


# ---------------------------------------------------------------------------
# 钉钉 → 飞书 转发管道测试
# ---------------------------------------------------------------------------

class TestHandleDingtalkMessage:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        plugin = _make_plugin()
        plugin.feishu_sender.send = AsyncMock(return_value=True)

        event = {
            "msgtype": "text",
            "msgId": "dt_msg_001",
            "senderNick": "Alice",
            "conversationId": "dt_group_1",
            "createAt": 1700000000000,
            "text": {"content": "Hello from DingTalk"},
        }

        await plugin.handle_dingtalk_message(event)

        plugin.feishu_sender.send.assert_called_once()
        assert plugin.stats.dingtalk_to_feishu_success == 1
        assert plugin.loop_detection.is_forwarded(
            ParsedMessage(
                message_id="dt_msg_001",
                sender_name="",
                send_time=datetime.now(tz=timezone.utc),
                source_id="",
                source_platform="dingtalk",
            )
        )

    @pytest.mark.asyncio
    async def test_loop_detection_skips_forwarded(self):
        plugin = _make_plugin()
        plugin.feishu_sender.send = AsyncMock(return_value=True)

        event = {
            "msgtype": "text",
            "msgId": "dt_msg_002",
            "senderNick": "Bob",
            "conversationId": "dt_group_1",
            "createAt": 1700000000000,
            "text": {"content": "[FWD] forwarded message"},
        }

        await plugin.handle_dingtalk_message(event)
        plugin.feishu_sender.send.assert_not_called()
        assert plugin.stats.dingtalk_to_feishu_success == 0

    @pytest.mark.asyncio
    async def test_no_matching_rule_skips(self):
        plugin = _make_plugin()
        plugin.feishu_sender.send = AsyncMock(return_value=True)

        event = {
            "msgtype": "text",
            "msgId": "dt_msg_003",
            "senderNick": "Carol",
            "conversationId": "unknown_group",
            "createAt": 1700000000000,
            "text": {"content": "No rule for this"},
        }

        await plugin.handle_dingtalk_message(event)
        plugin.feishu_sender.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_failure_records_stats(self):
        plugin = _make_plugin()
        plugin.feishu_sender.send = AsyncMock(return_value=False)

        event = {
            "msgtype": "text",
            "msgId": "dt_msg_004",
            "senderNick": "Dave",
            "conversationId": "dt_group_1",
            "createAt": 1700000000000,
            "text": {"content": "Will fail to send"},
        }

        await plugin.handle_dingtalk_message(event)
        assert plugin.stats.dingtalk_to_feishu_failure == 1
        assert plugin.stats.dingtalk_to_feishu_success == 0

    @pytest.mark.asyncio
    async def test_unsupported_msg_type_skips(self):
        plugin = _make_plugin()
        plugin.feishu_sender.send = AsyncMock(return_value=True)

        event = {
            "msgtype": "video",
            "msgId": "dt_msg_005",
            "senderNick": "Eve",
            "conversationId": "dt_group_1",
            "createAt": 1700000000000,
        }

        await plugin.handle_dingtalk_message(event)
        plugin.feishu_sender.send.assert_not_called()


# ---------------------------------------------------------------------------
# 飞书 → 钉钉 转发管道测试
# ---------------------------------------------------------------------------

class TestHandleFeishuMessage:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        plugin = _make_plugin()
        plugin.dingtalk_sender.send = AsyncMock(return_value=True)

        event = {
            "sender": {"sender_name": "张三", "sender_id": {}},
            "message": {
                "message_id": "fs_msg_001",
                "message_type": "text",
                "chat_id": "fs_chat_1",
                "create_time": "1700000000000",
                "content": '{"text": "Hello from Feishu"}',
            },
        }

        await plugin.handle_feishu_message(event)

        plugin.dingtalk_sender.send.assert_called_once()
        assert plugin.stats.feishu_to_dingtalk_success == 1

    @pytest.mark.asyncio
    async def test_loop_detection_skips_forwarded(self):
        plugin = _make_plugin()
        plugin.dingtalk_sender.send = AsyncMock(return_value=True)

        event = {
            "sender": {"sender_name": "李四", "sender_id": {}},
            "message": {
                "message_id": "fs_msg_002",
                "message_type": "text",
                "chat_id": "fs_chat_1",
                "create_time": "1700000000000",
                "content": '{"text": "[FWD] already forwarded"}',
            },
        }

        await plugin.handle_feishu_message(event)
        plugin.dingtalk_sender.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_matching_rule_skips(self):
        plugin = _make_plugin()
        plugin.dingtalk_sender.send = AsyncMock(return_value=True)

        event = {
            "sender": {"sender_name": "王五", "sender_id": {}},
            "message": {
                "message_id": "fs_msg_003",
                "message_type": "text",
                "chat_id": "unknown_chat",
                "create_time": "1700000000000",
                "content": '{"text": "No rule"}',
            },
        }

        await plugin.handle_feishu_message(event)
        plugin.dingtalk_sender.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_failure_records_stats(self):
        plugin = _make_plugin()
        plugin.dingtalk_sender.send = AsyncMock(return_value=False)

        event = {
            "sender": {"sender_name": "赵六", "sender_id": {}},
            "message": {
                "message_id": "fs_msg_004",
                "message_type": "text",
                "chat_id": "fs_chat_1",
                "create_time": "1700000000000",
                "content": '{"text": "Will fail"}',
            },
        }

        await plugin.handle_feishu_message(event)
        assert plugin.stats.feishu_to_dingtalk_failure == 1
        assert plugin.stats.feishu_to_dingtalk_success == 0

    @pytest.mark.asyncio
    async def test_exception_does_not_crash(self):
        """Handler 内部异常不应向外传播。"""
        plugin = _make_plugin()
        plugin.feishu_listener.on_message = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        # Should not raise
        await plugin.handle_feishu_message({"bad": "data"})


# ---------------------------------------------------------------------------
# 状态查询命令测试
# ---------------------------------------------------------------------------

class TestHandleStatusCommand:
    @pytest.mark.asyncio
    async def test_status_returns_stats_and_uptime(self):
        plugin = _make_plugin()
        # Record some stats
        plugin.stats.record(ForwardingDirection.DINGTALK_TO_FEISHU, True)
        plugin.stats.record(ForwardingDirection.DINGTALK_TO_FEISHU, True)
        plugin.stats.record(ForwardingDirection.DINGTALK_TO_FEISHU, False)
        plugin.stats.record(ForwardingDirection.FEISHU_TO_DINGTALK, True)
        plugin.stats.record(ForwardingDirection.FEISHU_TO_DINGTALK, False)
        plugin.stats.record(ForwardingDirection.FEISHU_TO_DINGTALK, False)

        result = await plugin.handle_status_command()

        assert "钉钉-飞书转发插件状态" in result
        assert "运行时长:" in result
        assert "成功: 2 条" in result  # d2f success
        assert "失败: 1 条" in result  # d2f failure (first occurrence)
        assert "钉钉 → 飞书" in result
        assert "飞书 → 钉钉" in result

    @pytest.mark.asyncio
    async def test_status_zero_counts_on_fresh_plugin(self):
        plugin = _make_plugin()

        result = await plugin.handle_status_command()

        assert "成功: 0 条" in result
        assert "失败: 0 条" in result
