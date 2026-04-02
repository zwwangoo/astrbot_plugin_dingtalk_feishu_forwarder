"""飞书消息发送器 - 通过飞书 Open API 发送消息"""

import asyncio
import json
import logging
import time
from typing import Optional

import aiohttp

from ..models import FeishuMessage, TokenCache

logger = logging.getLogger(__name__)

# 飞书 API 端点
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_SEND_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

# 重试配置
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # 指数退避：1s, 2s, 4s


class FeishuSender:
    """通过飞书 Open API 发送消息"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token_cache: Optional[TokenCache] = None

    async def send(self, message: FeishuMessage, target_id: str) -> bool:
        """
        发送消息到飞书目标。

        自动管理 tenant_access_token（过期自动刷新）。
        失败时重试最多 3 次，间隔 1s/2s/4s（指数退避）。

        Returns:
            是否发送成功
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                token = await self._get_valid_token()

                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "receive_id": target_id,
                        "msg_type": message.msg_type,
                        "content": json.dumps(message.content),
                    }
                    params = {"receive_id_type": "chat_id"}

                    async with session.post(
                        FEISHU_SEND_MSG_URL,
                        headers=headers,
                        json=payload,
                        params=params,
                    ) as resp:
                        data = await resp.json()
                        code = data.get("code", -1)

                        if code == 0:
                            logger.info(
                                "飞书消息发送成功: target=%s, msg_type=%s",
                                target_id,
                                message.msg_type,
                            )
                            return True

                        # Token 过期错误，刷新后重试
                        if code == 99991663 or code == 99991664:
                            logger.warning("飞书 token 已过期，正在刷新...")
                            self._token_cache = None
                            # 不消耗重试次数，直接继续下一轮
                            continue

                        logger.error(
                            "飞书 API 返回错误: code=%s, msg=%s",
                            code,
                            data.get("msg", ""),
                        )

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(
                    "飞书消息发送网络错误 (第 %d/%d 次): %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    str(e),
                )

            # 如果还有重试机会，等待后重试
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt]
                logger.info("将在 %d 秒后重试...", delay)
                await asyncio.sleep(delay)

        logger.error(
            "飞书消息发送最终失败: target=%s, msg_type=%s, 已重试 %d 次",
            target_id,
            message.msg_type,
            MAX_RETRIES,
        )
        return False

    async def _refresh_token(self) -> str:
        """获取或刷新 tenant_access_token"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            }
            async with session.post(
                FEISHU_TOKEN_URL,
                json=payload,
            ) as resp:
                data = await resp.json()
                code = data.get("code", -1)

                if code != 0:
                    raise RuntimeError(
                        f"获取飞书 tenant_access_token 失败: code={code}, msg={data.get('msg', '')}"
                    )

                token = data["tenant_access_token"]
                expire = data.get("expire", 7200)

                self._token_cache = TokenCache(
                    token=token,
                    expires_at=time.time() + expire,
                )

                logger.info("飞书 tenant_access_token 刷新成功, 有效期 %d 秒", expire)
                return token

    async def _get_valid_token(self) -> str:
        """获取有效的 token，过期时自动刷新"""
        if self._token_cache is None or self._token_cache.is_expired:
            return await self._refresh_token()
        return self._token_cache.token
