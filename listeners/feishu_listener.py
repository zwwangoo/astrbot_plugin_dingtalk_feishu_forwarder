"""飞书消息监听器"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from ..models import ContentElement, MessageType, ParsedMessage

logger = logging.getLogger(__name__)


class FeishuListener:
    """通过 AstrBot 适配层接收飞书消息"""

    SUPPORTED_MSG_TYPES = {"text", "post"}

    async def on_message(self, event: dict) -> Optional[ParsedMessage]:
        """
        解析飞书消息事件为 ParsedMessage。

        支持类型：text, post (image, file, link)
        不支持的类型记录警告并返回 None。
        解析失败记录错误（含原始消息摘要）并返回 None。
        """
        try:
            message = event.get("message", {})
            msg_type = message.get("message_type", "")

            if msg_type not in self.SUPPORTED_MSG_TYPES:
                logger.warning(
                    "不支持的飞书消息类型: %s，跳过该消息", msg_type
                )
                return None

            # 提取公共字段
            message_id = message.get("message_id", "")
            sender = event.get("sender", {})
            sender_name = sender.get("sender_name", "")
            sender_id_info = sender.get("sender_id", {})
            source_id = message.get("chat_id", "")

            # 解析发送时间（毫秒时间戳字符串）
            create_time_str = message.get("create_time", "0")
            try:
                timestamp_ms = int(create_time_str)
            except (ValueError, TypeError):
                timestamp_ms = 0
            send_time = datetime.fromtimestamp(
                timestamp_ms / 1000, tz=timezone.utc
            )

            # 解析消息内容 JSON 字符串
            content_str = message.get("content", "{}")
            content = json.loads(content_str)

            # 解析消息内容元素
            elements = self._parse_elements(content, msg_type)

            return ParsedMessage(
                message_id=message_id,
                sender_name=sender_name,
                send_time=send_time,
                source_id=source_id,
                source_platform="feishu",
                elements=elements,
                raw_data=event,
            )
        except Exception:
            raw_summary = str(event)[:200]
            logger.error(
                "飞书消息解析失败，原始消息摘要: %s", raw_summary, exc_info=True
            )
            return None

    def _parse_elements(
        self, content: dict, msg_type: str
    ) -> list[ContentElement]:
        """根据消息类型解析内容元素列表。"""
        if msg_type == "text":
            return self._parse_text(content)
        elif msg_type == "post":
            return self._parse_post(content)
        return []

    def _parse_text(self, content: dict) -> list[ContentElement]:
        """解析文本消息。"""
        text = content.get("text", "")
        return [ContentElement(type=MessageType.TEXT, text=text)]

    def _parse_post(self, content: dict) -> list[ContentElement]:
        """解析富文本（post）消息，支持文本、图片、文件、链接、@提及元素。"""
        elements: list[ContentElement] = []

        # post 内容结构: {"title": "...", "content": [[{tag, ...}, ...]]}
        paragraphs = content.get("content", [])

        for paragraph in paragraphs:
            if not isinstance(paragraph, list):
                continue
            for node in paragraph:
                tag = node.get("tag", "")

                if tag == "text":
                    elements.append(
                        ContentElement(
                            type=MessageType.TEXT, text=node.get("text", "")
                        )
                    )
                elif tag == "img":
                    elements.append(
                        ContentElement(
                            type=MessageType.IMAGE,
                            file_key=node.get("image_key", ""),
                        )
                    )
                elif tag == "file":
                    elements.append(
                        ContentElement(
                            type=MessageType.FILE,
                            file_key=node.get("file_key", ""),
                            file_name=node.get("file_name", ""),
                        )
                    )
                elif tag == "a":
                    elements.append(
                        ContentElement(
                            type=MessageType.LINK,
                            text=node.get("text", ""),
                            url=node.get("href", ""),
                        )
                    )
                elif tag == "at":
                    elements.append(
                        ContentElement(
                            type=MessageType.TEXT,
                            mention=node.get("user_name", ""),
                            text=f"@{node.get('user_name', '')}",
                        )
                    )
                else:
                    logger.warning(
                        "不支持的飞书富文本元素类型: %s，跳过", tag
                    )

        # 如果有标题，作为第一个元素插入
        title = content.get("title", "")
        if title:
            elements.insert(
                0, ContentElement(type=MessageType.TEXT, text=title)
            )

        return elements
