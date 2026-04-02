"""转发统计 - 运行状态监控与统计"""

import time

from ..models import ForwardingDirection


class ForwardingStats:
    """运行状态监控与统计"""

    def __init__(self):
        self.start_time: float = time.time()
        self.dingtalk_to_feishu_success: int = 0
        self.dingtalk_to_feishu_failure: int = 0
        self.feishu_to_dingtalk_success: int = 0
        self.feishu_to_dingtalk_failure: int = 0

    def record(self, direction: ForwardingDirection, success: bool) -> None:
        """记录一次转发结果"""
        if direction == ForwardingDirection.DINGTALK_TO_FEISHU:
            if success:
                self.dingtalk_to_feishu_success += 1
            else:
                self.dingtalk_to_feishu_failure += 1
        elif direction == ForwardingDirection.FEISHU_TO_DINGTALK:
            if success:
                self.feishu_to_dingtalk_success += 1
            else:
                self.feishu_to_dingtalk_failure += 1

    def get_summary(self) -> dict:
        """返回统计摘要，包含双向计数和运行时长"""
        uptime_seconds = time.time() - self.start_time
        return {
            "uptime_seconds": uptime_seconds,
            "dingtalk_to_feishu": {
                "success": self.dingtalk_to_feishu_success,
                "failure": self.dingtalk_to_feishu_failure,
            },
            "feishu_to_dingtalk": {
                "success": self.feishu_to_dingtalk_success,
                "failure": self.feishu_to_dingtalk_failure,
            },
        }
