"""飞书消息监听器单元测试"""

import json
import pytest

from listeners.feishu_listener import FeishuListener
from models import MessageType


def _make_event(msg_type: str, content: dict, **overrides) -> dict:
    """构造飞书消息事件。"""
    event = {
        "message": {
            "message_id": "msg_001",
            "message_type": msg_type,
            "content": json.dumps(content),
            "chat_id": "oc_chat_123",
            "create_time": "1700000000000",
        },
        "sender": {
            "sender_name": "张三",
            "sender_id": {
                "open_id": "ou_open_123",
                "user_id": "user_123",
            },
        },
    }
    event.update(overrides)
    return event


@pytest.fixture
def listener():
    return FeishuListener()


@pytest.mark.asyncio
async def test_parse_text_message(listener):
    """测试解析飞书文本消息。"""
    event = _make_event("text", {"text": "你好世界"})
    result = await listener.on_message(event)

    assert result is not None
    assert result.message_id == "msg_001"
    assert result.sender_name == "张三"
    assert result.source_id == "oc_chat_123"
    assert result.source_platform == "feishu"
    assert len(result.elements) == 1
    assert result.elements[0].type == MessageType.TEXT
    assert result.elements[0].text == "你好世界"


@pytest.mark.asyncio
async def test_parse_post_message_with_text_and_image(listener):
    """测试解析飞书富文本消息（含文本和图片）。"""
    content = {
        "title": "公告",
        "content": [
            [
                {"tag": "text", "text": "请查看附件"},
                {"tag": "img", "image_key": "img_key_001"},
            ]
        ],
    }
    event = _make_event("post", content)
    result = await listener.on_message(event)

    assert result is not None
    assert len(result.elements) == 3  # title + text + image
    assert result.elements[0].type == MessageType.TEXT
    assert result.elements[0].text == "公告"
    assert result.elements[1].type == MessageType.TEXT
    assert result.elements[1].text == "请查看附件"
    assert result.elements[2].type == MessageType.IMAGE
    assert result.elements[2].file_key == "img_key_001"


@pytest.mark.asyncio
async def test_parse_post_message_with_link_and_at(listener):
    """测试解析飞书富文本消息（含链接和@提及）。"""
    content = {
        "content": [
            [
                {"tag": "a", "text": "点击这里", "href": "https://example.com"},
                {"tag": "at", "user_name": "李四"},
            ]
        ],
    }
    event = _make_event("post", content)
    result = await listener.on_message(event)

    assert result is not None
    assert len(result.elements) == 2
    assert result.elements[0].type == MessageType.LINK
    assert result.elements[0].text == "点击这里"
    assert result.elements[0].url == "https://example.com"
    assert result.elements[1].type == MessageType.TEXT
    assert result.elements[1].mention == "李四"
    assert result.elements[1].text == "@李四"


@pytest.mark.asyncio
async def test_parse_post_message_with_file(listener):
    """测试解析飞书富文本消息（含文件）。"""
    content = {
        "content": [
            [
                {"tag": "file", "file_key": "fk_001", "file_name": "report.pdf"},
            ]
        ],
    }
    event = _make_event("post", content)
    result = await listener.on_message(event)

    assert result is not None
    assert len(result.elements) == 1
    assert result.elements[0].type == MessageType.FILE
    assert result.elements[0].file_key == "fk_001"
    assert result.elements[0].file_name == "report.pdf"


@pytest.mark.asyncio
async def test_unsupported_message_type_returns_none(listener):
    """测试不支持的消息类型返回 None。"""
    event = _make_event("image", {})
    event["message"]["message_type"] = "sticker"
    result = await listener.on_message(event)
    assert result is None


@pytest.mark.asyncio
async def test_parse_failure_returns_none(listener):
    """测试解析失败返回 None。"""
    # content 不是有效 JSON
    event = {
        "message": {
            "message_id": "msg_bad",
            "message_type": "text",
            "content": "not-valid-json{{{",
            "chat_id": "oc_chat_123",
            "create_time": "1700000000000",
        },
        "sender": {"sender_name": "test"},
    }
    result = await listener.on_message(event)
    assert result is None


@pytest.mark.asyncio
async def test_empty_event_returns_none(listener):
    """测试空事件返回 None（无 message_type 视为不支持）。"""
    result = await listener.on_message({})
    assert result is None


@pytest.mark.asyncio
async def test_timestamp_parsing(listener):
    """测试时间戳解析。"""
    event = _make_event("text", {"text": "hi"})
    event["message"]["create_time"] = "1700000000000"
    result = await listener.on_message(event)
    assert result is not None
    assert result.send_time.year == 2023
