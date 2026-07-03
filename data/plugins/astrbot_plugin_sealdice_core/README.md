# 海豹骰核心复刻

这是一个 AstrBot 插件，用来提供 SeaDice 风格的跑团骰子指令。插件默认使用 `.` 和 `。` 作为骰子指令前缀，保留 AstrBot 原生 `/` 指令。

## 安装

在 AstrBot 管理后台进入插件页面，上传本插件的 zip 包并启用插件。启用后可以使用 `/sealdice` 查看插件加载状态，使用 `/sealhelp` 或 `.help` 查看骰子帮助。

## 常用指令

- `.bot on` / `.bot off`：启用或关闭当前群的骰子响应。
- `.set coc` / `.set dnd`：切换当前群规则。
- `.nn 名字`：设置玩家昵称。
- `.pc new/load/save/list/del/tag`：管理人物卡。
- `.st hp=10 hp-1`：录入或扣减人物卡属性。
- `.cst` / `.dst`：查看 COC 或 DND 人物卡。
- `.r 1d100`：普通掷骰。
- `.ra 侦查` / `.rc 侦查`：COC 检定。
- `.sc 1/1d6`：理智检定。
- `.en` / `.ti` / `.li` / `.coc`：COC 辅助指令。
- `.dnd` / `.dndx` / `.ri` / `.init`：DND 辅助指令。
- `.buff` / `.ss` / `.cast` / `.longrest` / `.ds`：DND 状态、法术位和休息指令。
- `.log new/on/off/end/halt/list/get/del/stat/export`：跑团日志。
- `.draw 牌堆` / `.deck list/add/show/del`：抽牌和群内自定义牌堆。
- `.alias 名称 .指令` / `.&名称`：SeaDice 风格快捷指令。
- `.jrrp` / `.who` / `.name` / `.namednd`：娱乐和故事辅助工具。
- `.find 关键词` / `.helpdoc list/add/get/del` / `.matrix`：帮助文档和验收矩阵。
- `.reply` / `.ext` / `.js` / `.sealpack`：海豹扩展兼容层状态管理。
- `.black` / `.ban` / `.master` / `.team` / `.userid` / `.botlist`：群管理兼容入口。
- `.sn coc` / `.sn cocL` / `.sn dnd` / `.sn none` / `.sn off` / `.sn expr ...`：群名片模板。

## 路线配置

插件配置中可以设置 `route`：

- `python`：默认路线，继续使用当前 Python 复刻实现。
- `go_bridge`：通过 SeaDice `/sd-api/dice/exec` 和 `/sd-api/dice/recentMessage` 调用本地 Go 核心。
- `auto`：保留给后续稳定性探测，目前按 Python 路线运行。

`go_bridge_url` 和 `go_bridge_password` 用来连接本地 SeaDice 服务。SeaDice JS、牌堆、回复、helpdoc 和 `.sealpack` 作为兼容层记录状态；新扩展建议继续使用 AstrBot 插件体系。

## 说明

群名片修改会优先尝试 OneBot/QQ 适配器的 `set_group_card` 能力。适配器不支持时，插件会保留模板并返回预览，不影响其他骰子功能。

插件状态数据会保存在 AstrBot 插件数据目录中，不写入插件源码目录。
