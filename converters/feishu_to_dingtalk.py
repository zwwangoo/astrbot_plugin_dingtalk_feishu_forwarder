"""飞书到钉钉消息格式转换器"""

from ..models import ContentElement, DingTalkMessage, MessageType, ParsedMessage

FORWARD_TAG = "[FWD]"


class FeishuToDingTalkConverter:
    """将飞书消息格式转换为钉钉消息格式"""

    def convert(self, msg: ParsedMessage) -> DingTalkMessage:
        """
        转换飞书 ParsedMessage 为钉钉 DingTalkMessage。

        - 文本消息：转为钉钉文本格式，附加发送者和时间
        - 图片：飞书图片 Key 转为钉钉图片格式或含下载链接的文本
        - 文件：转为钉钉文件消息或含下载链接的文本
        - @提及：以文本形式保留
        - 添加 [FWD] 转发标识
        """
        send_time_str = msg.send_time.strftime("%Y-%m-%d %H:%M:%S")
        header = f"{FORWARD_TAG} {msg.sender_name} ({send_time_str}):"

        has_image = any(e.type == MessageType.IMAGE for e in msg.elements)
        has_file = any(e.type == MessageType.FILE for e in msg.elements)

        # Messages with images or files use actionCard format
        if has_image or has_file:
            return self._build_action_card_message(header, msg.elements)

        # Simple text-only messages
        return self._build_text_message(header, msg.elements)

    def _build_text_message(
        self, header: str, elements: list[ContentElement]
    ) -> DingTalkMessage:
        """构建纯文本钉钉消息。"""
        parts = [header]
        for elem in elements:
            part = self._element_to_text(elem)
            if part:
                parts.append(part)

        full_text = "\n".join(parts)
        return DingTalkMessage(
            msg_type="text",
            content={"content": full_text},
            forward_tag=FORWARD_TAG,
        )

    def _build_action_card_message(
        self, header: str, elements: list[ContentElement]
    ) -> DingTalkMessage:
        """构建 actionCard 钉钉消息，支持图片和文件混排（Markdown 格式）。"""
        parts = [header]

        for elem in elements:
            if elem.type == MessageType.TEXT:
                text = elem.text or ""
                if elem.mention:
                    text = f"@{elem.mention} {text}" if text else f"@{elem.mention}"
                if text:
                    parts.append(text)

            elif elem.type == MessageType.IMAGE:
                key = elem.file_key or elem.url or ""
                if key:
                    parts.append(f"![图片]({key})")
                else:
                    parts.append("[图片]")

            elif elem.type == MessageType.FILE:
                file_text = self._file_to_text(elem)
                if file_text:
                    parts.append(file_text)

            elif elem.type == MessageType.LINK:
                text = elem.text or elem.url or ""
                url = elem.url or ""
                if url and text:
                    parts.append(f"[{text}]({url})")
                elif text:
                    parts.append(text)

        markdown_text = "\n\n".join(parts)
        return DingTalkMessage(
            msg_type="actionCard",
            content={
                "title": header,
                "text": markdown_text,
            },
            forward_tag=FORWARD_TAG,
        )

    def _element_to_text(self, elem: ContentElement) -> str:
        """将内容元素转为纯文本表示。"""
        if elem.type == MessageType.TEXT:
            text = elem.text or ""
            if elem.mention:
                return f"@{elem.mention} {text}" if text else f"@{elem.mention}"
            return text

        if elem.type == MessageType.IMAGE:
            key = elem.file_key or elem.url or ""
            return f"[图片: {key}]" if key else "[图片]"

        if elem.type == MessageType.FILE:
            return self._file_to_text(elem)

        if elem.type == MessageType.LINK:
            text = elem.text or elem.url or ""
            url = elem.url or ""
            if url and text:
                return f"[{text}]({url})"
            return text

        return ""

    @staticmethod
    def _file_to_text(elem: ContentElement) -> str:
        """将文件元素转为文本描述（含下载链接）。"""
        name = elem.file_name or "未命名文件"
        url = elem.url or elem.file_key or ""
        if url:
            return f"[文件: {name}]({url})"
        return f"[文件: {name}]"
