# Lio 状态短视频

以 [JT 认可的 Lio 高清原件](../../lio/2026-11-25/README.md) 为参考，Codex 内置图像生成重画完整的全身姿势。第二轮先优化思考、查攻略和打招呼，增加蓄力和收势，让头部、身体、耳朵与绒毛错开运动。其余五段保留第一轮，等试片方向认可后采用相同做法。

| 状态 | 动作 | 全身关键帧 | MP4 | 首帧 |
| --- | --- | --- | --- | --- |
| 待机 | 呼吸时胸口与肩部轻轻起伏，中间眨一次眼 | 9，待优化 | [idle](lio-idle.mp4) | [PNG](lio-idle-still.png) |
| 思考 | 先蓄力，歪头抬眼，三个思考点依次出现，小跳后回正 | 23 | [thinking](lio-thinking.mp4) | [PNG](lio-thinking-still.png) |
| 查攻略 | 俯身读书，身体跟着翻页转动，抬头后耳朵和绒毛收势 | 22 | [searching](lio-searching.mp4) | [PNG](lio-searching-still.png) |
| 规划行程 | 展开地图，眼睛跟着朱红图钉落下，然后点头 | 9，待优化 | [planning](lio-planning.mp4) | [PNG](lio-planning-still.png) |
| 记住了 | 金色书签弹出，Lio 弹起、眯眼笑并点头 | 9，待优化 | [remembered](lio-remembered.mp4) | [PNG](lio-remembered-still.png) |
| 打招呼 | 先屈膝，抬脚弹起挥爪，落地后慢慢收势 | 22 | [greeting](lio-greeting.mp4) | [PNG](lio-greeting-still.png) |
| 多想一会儿 | 歪身挠头，放下爪子后点头 | 9，待优化 | [taking-longer](lio-taking-longer.mp4) | [PNG](lio-taking-longer-still.png) |
| 连接中断 | 收起爪子，略带歉意地低头，再抬头回正 | 9，待优化 | [offline](lio-offline.mp4) | [PNG](lio-offline-still.png) |

优化试片在不同动作阶段调整关键帧间隔，以 [Practical-RIFE 4.26](https://github.com/hzwer/Practical-RIFE#trained-model) 本机补帧。工具及作者发布的权重均采用 [MIT 许可](https://github.com/hzwer/Practical-RIFE/blob/main/LICENSE)。容易重影的快速动作重新画了全身中间姿势。编码使用本机 FFmpeg 9.0.1，构建启用了 GPL 和 version3，适用 [GPL-3.0-or-later](https://ffmpeg.org/legal.html)。

每段均为 720 × 720、30 fps、无音轨的 H.264 MP4，小于 1 MB。优化试片为 56 帧、约 1.87 秒，其余为 48 帧、1.60 秒。源底色为 `#FAF6EF`，8 bit YUV 4:2:0 经 ffmpeg 解码后纯色区域的蓝通道高 1。首末帧及对应 PNG 逐像素一致。

[八状态预览](lio-video-preview.png)取自实际动作帧。[manifest.json](manifest.json)记录大小、SHA-256、视频规格和全身关键帧数。
