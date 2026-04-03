"""AstrBot 钉钉-飞书双向消息转发插件入口"""

import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.event.filter import EventMessageType, PlatformAdapterType
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.message.components import BaseMessageComponent, At, Image, Plain
from astrbot.core.message.message_event_result import MessageChain

UNSUPPORTED_MSG_FALLBACK = "[不支持的消息类型，请在原平台查看]"


@register(
    "dingtalk_feishu_forwarder",
    "DingTalk-Feishu Forwarder",
    "钉钉-飞书双向消息转发插件",
    "1.0.0",
)
class DingTalkFeishuForwarder(Star):
    """钉钉与飞书之间的双向消息转发插件。

    收到钉钉消息 → 转发到飞书会话
    收到飞书消息 → 转发到钉钉会话
    """

    def __init__(self, context: Context, config=None):
        super().__init__(context)

        raw_config = dict(config) if config else {}

        self.feishu_target_session = raw_config.get("feishu_target_session", "")
        self.dingtalk_target_session = raw_config.get(
            "dingtalk_target_session", ""
        )
        self._enabled = bool(
            self.feishu_target_session or self.dingtalk_target_session
        )

        self._start_time = time.time()
        self._d2f_success = 0
        self._d2f_failure = 0
        self._f2d_success = 0
        self._f2d_failure = 0
        self._seen_messages: dict[str, float] = {}
        self._dedup_ttl = 30

        if self._enabled:
            logger.info(
                "钉钉-飞书转发插件已启用。feishu_target=%s, dingtalk_target=%s",
                self.feishu_target_session,
                self.dingtalk_target_session,
            )
        else:
            logger.warning(
                "钉钉-飞书转发插件未配置目标 session，请在插件配置中填写 "
                "feishu_target_session 和/或 dingtalk_target_session。"
                "可通过 /sid 命令在对应平台获取。"
            )

    def _is_bot_message(self, event: AstrMessageEvent) -> bool:
        """检查消息是否由机器人自身发送，防止回环。"""
        sender_id = event.get_sender_id()
        self_id = event.get_self_id()
        return bool(self_id and sender_id == self_id)

    def _is_duplicate(self, event: AstrMessageEvent) -> bool:
        """检查消息是否重复（按平台+会话+消息ID去重）。"""
        now = time.time()
        expired = [k for k, v in self._seen_messages.items() if now - v > self._dedup_ttl]
        for k in expired:
            del self._seen_messages[k]

        msg_obj = getattr(event, "message_obj", None)
        msg_id = getattr(msg_obj, "message_id", "") or ""
        if not msg_id:
            return False

        dedup_key = f"{event.get_platform_name()}:{event.session_id}:{msg_id}"
        if dedup_key in self._seen_messages:
            return True
        self._seen_messages[dedup_key] = now
        return False

    @filter.event_message_type(EventMessageType.ALL)
    @filter.platform_adapter_type(PlatformAdapterType.DINGTALK)
    async def on_dingtalk_message(self, event: AstrMessageEvent):
        """收到钉钉消息 → 转发到飞书"""
        if not self._enabled or not self.feishu_target_session:
            return
        if self._is_bot_message(event) or self._is_duplicate(event):
            return

        msg_str = event.get_message_str()
        messages = event.get_messages()
        if not msg_str and not messages:
            return

        logger.info("钉钉→飞书转发: session=%s", event.session_id)

        try:
            chain = self._build_forward_chain(messages, msg_str)
            await StarTools.send_message(self.feishu_target_session, chain)
            self._d2f_success += 1
            logger.info("钉钉→飞书转发成功")
            event.stop_event()
        except Exception:
            self._d2f_failure += 1
            logger.error("钉钉→飞书转发失败", exc_info=True)

    @filter.event_message_type(EventMessageType.ALL)
    @filter.platform_adapter_type(PlatformAdapterType.LARK)
    async def on_feishu_message(self, event: AstrMessageEvent):
        """收到飞书消息 → 转发到钉钉"""
        if not self._enabled or not self.dingtalk_target_session:
            return
        if self._is_bot_message(event) or self._is_duplicate(event):
            return

        msg_str = event.get_message_str()
        messages = event.get_messages()
        if not msg_str and not messages:
            return

        logger.info("飞书→钉钉转发: session=%s", event.session_id)

        try:
            chain = self._build_forward_chain(messages, msg_str)
            await StarTools.send_message(self.dingtalk_target_session, chain)
            self._f2d_success += 1
            logger.info("飞书→钉钉转发成功")
            event.stop_event()
        except Exception:
            self._f2d_failure += 1
            logger.error("飞书→钉钉转发失败", exc_info=True)

    @staticmethod
    def _build_forward_chain(
        messages: list[BaseMessageComponent], fallback_text: str
    ) -> MessageChain:
        """从原始消息链构建转发消息链。

        保留 Plain 文本组件；Image 组件尝试通过 URL 重建，
        无法重建时降级为文字提示。
        """
        if not messages:
            fallback = fallback_text.strip() if fallback_text.strip() else UNSUPPORTED_MSG_FALLBACK
            return MessageChain(chain=[Plain(fallback)])

        chain: list[BaseMessageComponent] = []
        has_unsupported = False
        for comp in messages:
            if isinstance(comp, Plain):
                chain.append(comp)
            elif isinstance(comp, At):
                pass  # @提及不转发，跳过即可
            elif isinstance(comp, Image):
                url = comp.url or comp.file or ""
                if url:
                    chain.append(Image.fromURL(url) if url.startswith("http") else Image(file=url))
                else:
                    chain.append(Plain("[图片无法转发，请在原平台查看]"))
            else:
                has_unsupported = True
                logger.debug("跳过未支持的消息组件: %s", type(comp).__name__)

        if has_unsupported and chain:
            chain.append(Plain("\n[包含未支持的消息组件，请在原平台查看完整内容]"))

        if not chain:
            fallback = fallback_text.strip() if fallback_text.strip() else UNSUPPORTED_MSG_FALLBACK
            return MessageChain(chain=[Plain(fallback)])

        return MessageChain(chain=chain)

    @filter.command("fwd_status")
    async def fwd_status(self, event: AstrMessageEvent):
        """查询转发插件运行状态"""
        uptime = time.time() - self._start_time
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        text = (
            f"📊 钉钉-飞书转发插件状态\n"
            f"运行时长: {hours}h {minutes}m {seconds}s\n"
            f"启用: {'是' if self._enabled else '否'}\n"
            f"\n钉钉 → 飞书: 成功 {self._d2f_success} / 失败 {self._d2f_failure}\n"
            f"飞书 → 钉钉: 成功 {self._f2d_success} / 失败 {self._f2d_failure}"
        )
        yield event.plain_result(text)
