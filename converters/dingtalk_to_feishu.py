"""钉钉到飞书消息格式转换器"""

from ..models import ContentElement, FeishuMessage, MessageType, ParsedMessage

FORWARD_TAG = "[FWD]"


class DingTalkToFeishuConverter:
    """将钉钉消息格式转换为飞书消息格式"""

    def convert(self, msg: ParsedMessage) -> FeishuMessage:
        """
        转换钉钉 ParsedMessage 为飞书 FeishuMessage。

        - 文本消息：转为飞书文本格式，附加发送者和时间
        - 图片：URL 转为飞书图片消息格式
        - 文件：转为含下载链接的文本
        - @提及：以文本形式保留
        - 添加 [FWD] 转发标识
        """
        send_time_str = msg.send_time.strftime("%Y-%m-%d %H:%M:%S")
        header = f"{FORWARD_TAG} {msg.sender_name} ({send_time_str}):"

        has_image = any(e.type == MessageType.IMAGE for e in msg.elements)
        has_file = any(e.type == MessageType.FILE for e in msg.elements)

        # Messages with images or files use rich text (post) format
        if has_image or has_file:
            return self._build_post_message(header, msg.elements)

        # Simple text-only messages
        return self._build_text_message(header, msg.elements)

    def _build_text_message(
        self, header: str, elements: list[ContentElement]
    ) -> FeishuMessage:
        """构建纯文本飞书消息。"""
        parts = [header]
        for elem in elements:
            part = self._element_to_text(elem)
            if part:
                parts.append(part)

        full_text = "\n".join(parts)
        return FeishuMessage(
            msg_type="text",
            content={"text": full_text},
            forward_tag=FORWARD_TAG,
        )

    def _build_post_message(
        self, header: str, elements: list[ContentElement]
    ) -> FeishuMessage:
        """构建富文本（post）飞书消息，支持图片和文件混排。"""
        content_nodes: list[list[dict]] = []

        # Header line
        content_nodes.append([{"tag": "text", "text": header}])

        # Content elements
        line: list[dict] = []
        for elem in elements:
            if elem.type == MessageType.TEXT:
                text = elem.text or ""
                if elem.mention:
                    text = f"@{elem.mention} {text}" if text else f"@{elem.mention}"
                if text:
                    line.append({"tag": "text", "text": text})

            elif elem.type == MessageType.IMAGE:
                # Flush current line before image
                if line:
                    content_nodes.append(line)
                    line = []
                img_node: dict = {"tag": "img"}
                if elem.file_key:
                    img_node["image_key"] = elem.file_key
                elif elem.url:
                    img_node["image_key"] = elem.url
                content_nodes.append([img_node])

            elif elem.type == MessageType.FILE:
                file_text = self._file_to_text(elem)
                if file_text:
                    line.append({"tag": "text", "text": file_text})

            elif elem.type == MessageType.LINK:
                link_text = elem.text or elem.url or ""
                url = elem.url or ""
                if url:
                    line.append({"tag": "a", "text": link_text, "href": url})
                elif link_text:
                    line.append({"tag": "text", "text": link_text})

        if line:
            content_nodes.append(line)

        return FeishuMessage(
            msg_type="post",
            content={
                "post": {
                    "zh_cn": {
                        "content": content_nodes,
                    }
                }
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
            url = elem.url or elem.file_key or ""
            return f"[图片: {url}]" if url else "[图片]"

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
