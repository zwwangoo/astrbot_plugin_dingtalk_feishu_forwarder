"""钉钉消息监听器"""

import logging
from datetime import datetime, timezone
from typing import Optional

from ..models import ContentElement, MessageType, ParsedMessage

logger = logging.getLogger(__name__)


class DingTalkListener:
    """通过 AstrBot 适配层接收钉钉消息"""

    SUPPORTED_MSG_TYPES = {"text", "richText"}

    async def on_message(self, event: dict) -> Optional[ParsedMessage]:
        """
        解析钉钉消息事件为 ParsedMessage。

        支持类型：text, richText (image, file, link)
        不支持的类型记录警告并返回 None。
        解析失败记录错误（含原始消息摘要）并返回 None。
        """
        try:
            msg_type = event.get("msgtype", "")

            if msg_type not in self.SUPPORTED_MSG_TYPES:
                logger.warning(
                    "不支持的钉钉消息类型: %s，跳过该消息", msg_type
                )
                return None

            # 提取公共字段
            message_id = event.get("msgId", "")
            sender_name = event.get("senderNick", "")
            source_id = event.get("conversationId", "")

            # 解析发送时间（毫秒时间戳）
            timestamp_ms = event.get("createAt") or event.get("sendTime") or 0
            send_time = datetime.fromtimestamp(
                timestamp_ms / 1000, tz=timezone.utc
            )

            # 解析消息内容元素
            elements = self._parse_elements(event, msg_type)

            return ParsedMessage(
                message_id=message_id,
                sender_name=sender_name,
                send_time=send_time,
                source_id=source_id,
                source_platform="dingtalk",
                elements=elements,
                raw_data=event,
            )
        except Exception:
            raw_summary = str(event)[:200]
            logger.error(
                "钉钉消息解析失败，原始消息摘要: %s", raw_summary, exc_info=True
            )
            return None

    def _parse_elements(
        self, event: dict, msg_type: str
    ) -> list[ContentElement]:
        """根据消息类型解析内容元素列表。"""
        if msg_type == "text":
            return self._parse_text(event)
        elif msg_type == "richText":
            return self._parse_rich_text(event)
        return []

    def _parse_text(self, event: dict) -> list[ContentElement]:
        """解析文本消息。"""
        text_content = event.get("text", {}).get("content", "")
        return [ContentElement(type=MessageType.TEXT, text=text_content)]

    def _parse_rich_text(self, event: dict) -> list[ContentElement]:
        """解析富文本消息，支持文本、图片、文件、链接元素。"""
        elements: list[ContentElement] = []
        rich_text_items = event.get("richText", [])

        for item in rich_text_items:
            item_type = item.get("type", "")

            if item_type == "text":
                elements.append(
                    ContentElement(
                        type=MessageType.TEXT, text=item.get("text", "")
                    )
                )
            elif item_type == "picture":
                elements.append(
                    ContentElement(
                        type=MessageType.IMAGE,
                        url=item.get("downloadCode") or item.get("url", ""),
                    )
                )
            elif item_type == "file":
                elements.append(
                    ContentElement(
                        type=MessageType.FILE,
                        url=item.get("downloadCode") or item.get("url", ""),
                        file_name=item.get("fileName", ""),
                        file_key=item.get("fileKey", ""),
                    )
                )
            elif item_type == "link":
                elements.append(
                    ContentElement(
                        type=MessageType.LINK,
                        text=item.get("text", ""),
                        url=item.get("url", ""),
                    )
                )
            else:
                logger.warning(
                    "不支持的钉钉富文本元素类型: %s，跳过", item_type
                )

        return elements
