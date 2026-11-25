# Lio 状态动图

以 [JT 认可的 Lio 高清原件](../../lio/2026-11-25/README.md) 为基准。Codex 内置图像生成提供眼睑、视线、爪子和道具素材，Pillow 将它们与同一套头部和肩部图层合成。八种状态各 11 帧，512 × 512，纯色 `#FAF6EF`，无限循环，首末帧画面相同。待机为 1.82 秒，其余为 1.87 秒。每张静态 PNG 都使用对应 GIF 的第一帧。

| 状态 | 动作 | GIF | 首帧 |
| --- | --- | --- | --- |
| 待机 | 轻轻呼吸，中间眨一次眼 | [idle](lio-idle.gif) | [PNG](lio-idle-still.png) |
| 思考 | 歪头向上看，三个小点依次亮起 | [thinking](lio-thinking.gif) | [PNG](lio-thinking-still.png) |
| 查攻略 | 捧着旅行书翻一页 | [searching](lio-searching.gif) | [PNG](lio-searching-still.png) |
| 规划行程 | 低眼看地图，朱红图钉落下，然后点头 | [planning](lio-planning.gif) | [PNG](lio-planning-still.png) |
| 记住了 | 金色书签弹出，Lio 微笑点头 | [remembered](lio-remembered.gif) | [PNG](lio-remembered-still.png) |
| 打招呼 | 举起一只爪子挥一下 | [greeting](lio-greeting.gif) | [PNG](lio-greeting-still.png) |
| 多想一会儿 | 用爪子挠一下头，再点头 | [taking-longer](lio-taking-longer.gif) | [PNG](lio-taking-longer-still.png) |
| 连接中断 | 带点歉意地低头，再抬头 | [offline](lio-offline.gif) | [PNG](lio-offline-still.png) |

[八状态预览拼图](lio-motion-preview.png)使用各动图实际动作中的一帧。[manifest.json](manifest.json)记录文件大小、SHA-256 和动图规格。
