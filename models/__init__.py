# 数据模型
"""钉钉-飞书双向消息转发插件数据模型定义"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ForwardingDirection(str, Enum):
    """转发方向枚举"""
    DINGTALK_TO_FEISHU = "dingtalk_to_feishu"
    FEISHU_TO_DINGTALK = "feishu_to_dingtalk"


class MessageType(str, Enum):
    """消息类型枚举"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    LINK = "link"
    RICH_TEXT = "rich_text"


@dataclass
class ContentElement:
    """内容元素"""
    type: MessageType
    text: Optional[str] = None
    url: Optional[str] = None
    file_key: Optional[str] = None
    file_name: Optional[str] = None
    mention: Optional[str] = None  # @提及的用户名


@dataclass
class ParsedMessage:
    """统一消息模型"""
    message_id: str
    sender_name: str
    send_time: datetime
    source_id: str              # 来源会话标识
    source_platform: str        # "dingtalk" 或 "feishu"
    elements: list[ContentElement] = field(default_factory=list)
    raw_data: Optional[dict] = None


@dataclass
class FeishuMessage:
    """飞书消息"""
    msg_type: str       # "text", "image", "file", "interactive"
    content: dict = field(default_factory=dict)
    forward_tag: str = ""  # 转发标识


@dataclass
class DingTalkMessage:
    """钉钉消息"""
    msg_type: str       # "text", "image", "file", "actionCard"
    content: dict = field(default_factory=dict)
    forward_tag: str = ""  # 转发标识


@dataclass
class ForwardingRule:
    """转发规则"""
    direction: ForwardingDirection
    source_id: str          # 来源群组/会话 ID
    target_id: str          # 目标群组/会话 ID
    is_global: bool = False  # 是否为全局转发规则


@dataclass
class TokenCache:
    """Token 缓存"""
    token: str
    expires_at: float   # Unix 时间戳

    @property
    def is_expired(self) -> bool:
        """检查 token 是否过期（提前 60 秒刷新）"""
        return time.time() >= self.expires_at - 60


__all__ = [
    "ForwardingDirection",
    "MessageType",
    "ContentElement",
    "ParsedMessage",
    "FeishuMessage",
    "DingTalkMessage",
    "ForwardingRule",
    "TokenCache",
]
