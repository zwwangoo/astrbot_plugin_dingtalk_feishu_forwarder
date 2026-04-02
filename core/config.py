"""插件配置管理"""

import logging
from ..models import ForwardingDirection, ForwardingRule

logger = logging.getLogger(__name__)


class PluginConfig:
    """插件配置管理，从 AstrBot 配置字典加载和验证配置。"""

    REQUIRED_FIELDS = [
        "dingtalk_app_key",
        "dingtalk_app_secret",
        "feishu_app_id",
        "feishu_app_secret",
    ]

    def __init__(self, raw_config: dict):
        """从 AstrBot 配置字典初始化"""
        self._raw = raw_config

    def validate(self) -> tuple[bool, str]:
        """
        验证配置完整性。
        返回 (is_valid, error_message)。
        必填字段：dingtalk_app_key, dingtalk_app_secret, feishu_app_id, feishu_app_secret
        """
        missing = [f for f in self.REQUIRED_FIELDS if not self._raw.get(f)]
        if missing:
            msg = f"缺少必要配置字段: {', '.join(missing)}"
            return False, msg

        raw_rules = self._raw.get("forwarding_rules", [])
        if not raw_rules:
            logger.warning("转发规则为空，插件将以无转发规则状态运行")

        return True, ""

    @property
    def forwarding_rules(self) -> list[ForwardingRule]:
        """获取转发规则列表"""
        rules: list[ForwardingRule] = []
        raw_rules = self._raw.get("forwarding_rules", [])
        for item in raw_rules:
            try:
                direction = ForwardingDirection(item["direction"])
                rules.append(ForwardingRule(
                    direction=direction,
                    source_id=item["source_id"],
                    target_id=item["target_id"],
                    is_global=item.get("is_global", False),
                ))
            except (KeyError, ValueError) as e:
                logger.warning("跳过无效的转发规则 %s: %s", item, e)
        return rules
