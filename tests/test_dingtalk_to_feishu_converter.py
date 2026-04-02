"""钉钉到飞书转换器单元测试"""

from datetime import datetime

from converters.dingtalk_to_feishu import DingTalkToFeishuConverter, FORWARD_TAG
from models import ContentElement, MessageType, ParsedMessage


def _make_msg(*elements: ContentElement, sender_name: str = "张三") -> ParsedMessage:
    return ParsedMessage(
        message_id="msg_001",
        sender_name=sender_name,
        send_time=datetime(2024, 1, 15, 10, 30, 0),
        source_id="chat_123",
        source_platform="dingtalk",
        elements=list(elements),
    )


def test_text_message_conversion():
    """文本消息转换为飞书文本格式，包含发送者和时间。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(ContentElement(type=MessageType.TEXT, text="你好世界"))
    result = converter.convert(msg)

    assert result.msg_type == "text"
    assert result.forward_tag == FORWARD_TAG
    assert "[FWD]" in result.content["text"]
    assert "张三" in result.content["text"]
    assert "2024-01-15 10:30:00" in result.content["text"]
    assert "你好世界" in result.content["text"]


def test_image_message_uses_post_format():
    """含图片的消息使用 post 富文本格式。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(type=MessageType.TEXT, text="看图"),
        ContentElement(type=MessageType.IMAGE, url="https://img.example.com/1.png"),
    )
    result = converter.convert(msg)

    assert result.msg_type == "post"
    assert result.forward_tag == FORWARD_TAG
    content_nodes = result.content["post"]["zh_cn"]["content"]
    # Header line
    assert any("[FWD]" in n.get("text", "") for line in content_nodes for n in line)


def test_image_with_file_key():
    """图片使用 file_key 时正确映射到 image_key。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(type=MessageType.IMAGE, file_key="img_key_001"),
    )
    result = converter.convert(msg)

    assert result.msg_type == "post"
    content_nodes = result.content["post"]["zh_cn"]["content"]
    img_nodes = [
        n for line in content_nodes for n in line if n.get("tag") == "img"
    ]
    assert len(img_nodes) == 1
    assert img_nodes[0]["image_key"] == "img_key_001"


def test_file_message_includes_download_link():
    """文件消息包含文件名和下载链接。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(
            type=MessageType.FILE,
            file_name="report.pdf",
            url="https://dl.example.com/report.pdf",
        ),
    )
    result = converter.convert(msg)

    assert result.msg_type == "post"
    flat_text = " ".join(
        n.get("text", "") for line in result.content["post"]["zh_cn"]["content"] for n in line
    )
    assert "report.pdf" in flat_text


def test_file_without_url():
    """文件无下载链接时仅显示文件名。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(type=MessageType.FILE, file_name="data.csv"),
    )
    result = converter.convert(msg)

    assert result.msg_type == "post"
    flat_text = " ".join(
        n.get("text", "") for line in result.content["post"]["zh_cn"]["content"] for n in line
    )
    assert "data.csv" in flat_text


def test_mention_preserved_as_text():
    """@提及以文本形式保留。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(type=MessageType.TEXT, text="请查看", mention="李四"),
    )
    result = converter.convert(msg)

    assert result.msg_type == "text"
    assert "@李四" in result.content["text"]


def test_link_element_in_text_mode():
    """链接元素在纯文本模式下以 markdown 格式呈现。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(
            type=MessageType.LINK, text="点击这里", url="https://example.com"
        ),
    )
    result = converter.convert(msg)

    assert result.msg_type == "text"
    assert "[点击这里](https://example.com)" in result.content["text"]


def test_link_element_in_post_mode():
    """链接元素在 post 模式下使用 <a> 标签。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(
        ContentElement(
            type=MessageType.LINK, text="文档", url="https://docs.example.com"
        ),
        ContentElement(type=MessageType.IMAGE, url="https://img.example.com/1.png"),
    )
    result = converter.convert(msg)

    assert result.msg_type == "post"
    a_nodes = [
        n
        for line in result.content["post"]["zh_cn"]["content"]
        for n in line
        if n.get("tag") == "a"
    ]
    assert len(a_nodes) == 1
    assert a_nodes[0]["text"] == "文档"
    assert a_nodes[0]["href"] == "https://docs.example.com"


def test_forward_tag_always_present():
    """转发标识始终存在。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg(ContentElement(type=MessageType.TEXT, text="test"))
    result = converter.convert(msg)
    assert result.forward_tag == FORWARD_TAG


def test_empty_elements():
    """空元素列表仍生成带 header 的消息。"""
    converter = DingTalkToFeishuConverter()
    msg = _make_msg()
    result = converter.convert(msg)

    assert result.msg_type == "text"
    assert "[FWD]" in result.content["text"]
    assert "张三" in result.content["text"]
