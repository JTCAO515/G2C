# Lio 状态短视频

以 [JT 认可的 Lio 高清原件](../../lio/2026-11-25/README.md) 为参考，Codex 内置图像生成分别重画每个状态的九个完整全身姿势。轻微的整体位移、倾斜和压缩拉伸连接这些姿势，再用 ffmpeg 编码。播放器可重复播放，解码后的首末帧逐像素一致。

| 状态 | 动作 | MP4 | 首帧 |
| --- | --- | --- | --- |
| 待机 | 呼吸时胸口与肩部轻轻起伏，中间眨一次眼 | [idle](lio-idle.mp4) | [PNG](lio-idle-still.png) |
| 思考 | 压低身体，歪头上看，三个思考点依次出现，小跳后回正 | [thinking](lio-thinking.mp4) | [PNG](lio-thinking-still.png) |
| 查攻略 | 俯身读书，身体随翻页转动，看到新一页后抬头笑 | [searching](lio-searching.mp4) | [PNG](lio-searching-still.png) |
| 规划行程 | 展开地图，眼睛跟着朱红图钉落下，然后点头 | [planning](lio-planning.mp4) | [PNG](lio-planning-still.png) |
| 记住了 | 金色书签弹出，Lio 弹起、眯眼笑并点头 | [remembered](lio-remembered.mp4) | [PNG](lio-remembered-still.png) |
| 打招呼 | 屈膝弹起，歪头、抬脚挥爪，落地后回到站姿 | [greeting](lio-greeting.mp4) | [PNG](lio-greeting-still.png) |
| 多想一会儿 | 歪身挠头，放下爪子后点头 | [taking-longer](lio-taking-longer.mp4) | [PNG](lio-taking-longer-still.png) |
| 连接中断 | 收起爪子，略带歉意地低头，再抬头回正 | [offline](lio-offline.mp4) | [PNG](lio-offline-still.png) |

每段为 720 × 720、30 fps、48 帧、1.6 秒、无音轨的 H.264 MP4，单段小于 1 MB。源帧底色为 `#FAF6EF`。为兼容播放器使用 8 bit YUV 4:2:0 编码，ffmpeg 解码后纯色区域的蓝通道高 1。PNG 从各 MP4 解码导出，与视频的第一帧一致。

[八状态预览](lio-video-preview.png)由实际动作帧组成。[manifest.json](manifest.json)记录文件大小、SHA-256 和视频规格。
