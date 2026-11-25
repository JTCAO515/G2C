# Lio 状态短视频

以 [JT 认可的 Lio 高清原件](../../lio/2026-11-25/README.md) 为参考，每个状态整理 64 张完整的全身绘制姿势。动作起步和收势放缓，头部、身体、耳朵和绒毛有先后。快速转头、翻页、起跳和落地附近加画了全身姿势。

| 状态 | 动作 | MP4 | 首帧 |
| --- | --- | --- | --- |
| 待机 | 呼吸时胸口与肩部轻轻起伏，中间眨一次眼 | [idle](lio-idle.mp4) | [PNG](lio-idle-still.png) |
| 思考 | 先蓄力，歪头抬眼，三个思考点依次出现，小跳后回正 | [thinking](lio-thinking.mp4) | [PNG](lio-thinking-still.png) |
| 查攻略 | 俯身读书，身体跟着翻页转动，抬头后耳朵和绒毛收势 | [searching](lio-searching.mp4) | [PNG](lio-searching-still.png) |
| 规划行程 | 展开地图，目光跟着朱红图钉落下，然后点头 | [planning](lio-planning.mp4) | [PNG](lio-planning-still.png) |
| 记住了 | 金色书签弹出，Lio 弹起、眯眼笑并点头 | [remembered](lio-remembered.mp4) | [PNG](lio-remembered-still.png) |
| 打招呼 | 先屈膝，抬脚弹起挥爪，落地后慢慢收势 | [greeting](lio-greeting.mp4) | [PNG](lio-greeting-still.png) |
| 多想一会儿 | 歪身挠头，放下爪子后点头 | [taking-longer](lio-taking-longer.mp4) | [PNG](lio-taking-longer-still.png) |
| 连接中断 | 收起爪子，略带歉意地低头，再抬头回正 | [offline](lio-offline.mp4) | [PNG](lio-offline-still.png) |

Codex 内置图像生成提供全身姿势，[Practical-RIFE 4.26](https://github.com/hzwer/Practical-RIFE#trained-model) 在本机补间。工具及作者发布的权重均采用 [MIT 许可](https://github.com/hzwer/Practical-RIFE/blob/main/LICENSE)。FFmpeg 9.0.1 的本机构建启用了 GPL 和 version3，适用 [GPL-3.0-or-later](https://ffmpeg.org/legal.html)。

每段为 720 × 720、30 fps、60 帧、2 秒、无音轨的 H.264 MP4，小于 1 MB。64 张源姿势用于绘制动作过程，再按成片规格采样。对应的首帧 PNG 与视频首末帧逐像素一致。源底色为 `#FAF6EF`，8 bit YUV 4:2:0 经 ffmpeg 解码后纯色区域的蓝通道高 1。

[八状态预览](lio-video-preview.png)取自成片实际动作帧。[manifest.json](manifest.json)记录文件大小、SHA-256 和视频规格。
