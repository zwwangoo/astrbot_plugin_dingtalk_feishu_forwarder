"""规则匹配器：根据转发规则匹配消息目标"""

from ..models import ForwardingDirection, ForwardingRule


class RuleMatcher:
    """根据转发规则匹配消息目标"""

    def __init__(self, rules: list[ForwardingRule]):
        self._rules = rules

    def match(self, source_id: str, direction: ForwardingDirection) -> list[str]:
        """
        根据来源会话 ID 和转发方向匹配目标。
        返回所有匹配的目标 ID 列表（可能为空）。
        全局转发模式下返回该方向的默认目标。
        """
        target_ids: list[str] = []
        for rule in self._rules:
            if rule.direction != direction:
                continue
            if rule.is_global or rule.source_id == source_id:
                target_ids.append(rule.target_id)
        return target_ids
