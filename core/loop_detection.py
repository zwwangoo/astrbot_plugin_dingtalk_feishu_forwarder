"""循环检测模块 - 防止消息在双向转发中被无限循环转发"""

import logging
import time

from ..models import ParsedMessage

logger = logging.getLogger(__name__)


class LoopDetection:
    """防止消息循环转发"""

    FORWARD_TAG = "[FWD]"
    CACHE_TTL = 300  # 5 分钟

    def __init__(self) -> None:
        # message_id -> timestamp
        self._forwarded_cache: dict[str, float] = {}

    def is_forwarded(self, message: ParsedMessage) -> bool:
        """
        检查消息是否为转发消息。
        检查条件：
        1. 消息内容包含转发标识标记
        2. 消息 ID 存在于已转发缓存中
        """
        self._cleanup_expired()

        # Check content for forward tag
        for element in message.elements:
            if element.text and self.FORWARD_TAG in element.text:
                logger.warning(
                    "检测到循环转发（转发标记）: message_id=%s, source=%s, platform=%s",
                    message.message_id,
                    message.source_id,
                    message.source_platform,
                )
                return True

        # Check forwarded cache
        if message.message_id in self._forwarded_cache:
            logger.warning(
                "检测到循环转发（缓存命中）: message_id=%s, source=%s, platform=%s",
                message.message_id,
                message.source_id,
                message.source_platform,
            )
            return True

        return False

    def mark_as_forwarded(self, message_id: str) -> None:
        """将消息 ID 加入已转发缓存"""
        self._forwarded_cache[message_id] = time.time()

    def _cleanup_expired(self) -> None:
        """清理过期的缓存条目"""
        now = time.time()
        expired_keys = [
            mid for mid, ts in self._forwarded_cache.items()
            if now - ts > self.CACHE_TTL
        ]
        for key in expired_keys:
            del self._forwarded_cache[key]
