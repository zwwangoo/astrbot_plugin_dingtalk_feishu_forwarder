# 钉钉-飞书双向消息转发插件

AstrBot 插件，实现钉钉与飞书之间的双向消息转发。

## 功能

- 钉钉单聊/群聊消息自动转发到飞书
- 飞书单聊/群聊消息自动转发到钉钉
- 转发内容为纯原始消息，无额外前缀
- 内置循环检测，防止消息风暴
- `/fwd_status` 命令查看转发统计

## 前置条件

1. AstrBot 已接入钉钉平台适配器（[接入文档](https://docs.astrbot.app/platform/dingtalk.html)）
2. AstrBot 已接入飞书平台适配器（[接入文档](https://docs.astrbot.app/platform/lark.html)）
3. 飞书机器人需开启"与用户单聊"权限（如需单聊转发）

## 配置

安装插件后，在插件配置页面填写两个字段：

| 字段 | 说明 |
|------|------|
| `feishu_target_session` | 飞书目标会话，接收钉钉转发过来的消息 |
| `dingtalk_target_session` | 钉钉目标会话，接收飞书转发过来的消息 |

### 获取 session 值

在对应平台的对话中发送 `/sid` 命令（飞书群聊需 @机器人），机器人会回复 UMO 值，格式如：

- 钉钉：`dingtalk:FriendMessage:kE2T0Ic/xxxxx`
- 飞书：`lark:FriendMessage:ou_xxxxx`

将获取到的 UMO 值填入对应配置项，保存后重载插件即可。
