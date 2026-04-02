"""钉钉消息发送器 - 通过钉钉 API 发送消息"""

import asyncio
import logging
import time
from typing import Optional

import aiohttp

from ..models import DingTalkMessage, TokenCache

logger = logging.getLogger(__name__)

# 钉钉 API 端点
DINGTALK_TOKEN_URL = "https://oapi.dingtalk.com/gettoken"
DINGTALK_SEND_MSG_URL = "https://oapi.dingtalk.com/chat/send"

# 重试配置
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # 指数退避：1s, 2s, 4s


class DingTalkSender:
    """通过钉钉 API 发送消息"""

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self._token_cache: Optional[TokenCache] = None

    async def send(self, message: DingTalkMessage, target_id: str) -> bool:
        """
        发送消息到钉钉目标。

        自动管理 access_token（过期自动刷新）。
        失败时重试最多 3 次，间隔 1s/2s/4s（指数退避）。

        Returns:
            是否发送成功
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                token = await self._get_valid_token()

                async with aiohttp.ClientSession() as session:
                    headers = {"Content-Type": "application/json"}
                    params = {"access_token": token}
                    payload = {
                        "chatid": target_id,
                        "msg": {
                            "msgtype": message.msg_type,
                            message.msg_type: message.content,
                        },
                    }

                    async with session.post(
                        DINGTALK_SEND_MSG_URL,
                        headers=headers,
                        json=payload,
                        params=params,
                    ) as resp:
                        data = await resp.json()
                        errcode = data.get("errcode", -1)

                        if errcode == 0:
                            logger.info(
                                "钉钉消息发送成功: target=%s, msg_type=%s",
                                target_id,
                                message.msg_type,
                            )
                            return True

                        # Token 过期/无效错误，刷新后重试
                        if errcode in (88, 40014, 40001):
                            logger.warning("钉钉 access_token 已过期，正在刷新...")
                            self._token_cache = None
                            continue

                        logger.error(
                            "钉钉 API 返回错误: errcode=%s, errmsg=%s",
                            errcode,
                            data.get("errmsg", ""),
                        )

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(
                    "钉钉消息发送网络错误 (第 %d/%d 次): %s",
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
            "钉钉消息发送最终失败: target=%s, msg_type=%s, 已重试 %d 次",
            target_id,
            message.msg_type,
            MAX_RETRIES,
        )
        return False

    async def _refresh_token(self) -> str:
        """获取或刷新 access_token"""
        async with aiohttp.ClientSession() as session:
            params = {
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            }
            async with session.get(
                DINGTALK_TOKEN_URL,
                params=params,
            ) as resp:
                data = await resp.json()
                errcode = data.get("errcode", -1)

                if errcode != 0:
                    raise RuntimeError(
                        f"获取钉钉 access_token 失败: errcode={errcode}, errmsg={data.get('errmsg', '')}"
                    )

                token = data["access_token"]
                expires_in = data.get("expires_in", 7200)

                self._token_cache = TokenCache(
                    token=token,
                    expires_at=time.time() + expires_in,
                )

                logger.info("钉钉 access_token 刷新成功, 有效期 %d 秒", expires_in)
                return token

    async def _get_valid_token(self) -> str:
        """获取有效的 token，过期时自动刷新"""
        if self._token_cache is None or self._token_cache.is_expired:
            return await self._refresh_token()
        return self._token_cache.token
