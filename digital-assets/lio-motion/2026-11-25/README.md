# Lio 状态短视频

采用 [JT 认可的 Lio 高清原件](../../lio/2026-11-25/README.md)。Codex 内置图像生成给每个状态重画九个完整的全身姿势。用轻微的整体位移、倾斜和压缩拉伸连接姿势，再用 ffmpeg 编码。最后一帧回到开场姿势，播放器可无缝循环。

| 状态 | 动作 | MP4 | 首帧 |
| --- | --- | --- | --- |
| 思考 | 压低身体，歪头上看，三个思考点依次出现，小跳后回正 | [thinking](lio-thinking.mp4) | [PNG](lio-thinking-still.png) |
| 查攻略 | 俯身读书，身体随翻页转动，看到新一页后抬头笑 | [searching](lio-searching.mp4) | [PNG](lio-searching-still.png) |
| 打招呼 | 屈膝弹起，歪头、抬脚挥爪，落地后回到站姿 | [greeting](lio-greeting.mp4) | [PNG](lio-greeting-still.png) |

每段为 720 × 720、30 fps、1.6 秒、无音轨的 H.264 MP4。源帧底色为 `#FAF6EF`。为兼容播放器使用 8 bit YUV 4:2:0 编码，ffmpeg 解码后纯色区域的蓝通道高 1。首帧 PNG 从各 MP4 解码导出，与最终视频的第一帧一致。

[试片预览](lio-video-preview.png)取自动作中的实际帧。[manifest.json](manifest.json)记录文件大小、SHA-256 和视频规格。
