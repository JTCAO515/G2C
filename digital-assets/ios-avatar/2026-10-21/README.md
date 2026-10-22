# iOS 头像原件归档

来源：用户 JT 于 2026-10-21 上传，指定作为 iOS App 头像数字资产保存。本目录仅保存原件及核验元数据，未接入或替换 App 代码，未生成、重绘、缩放或转换图片。

App 品牌仍为 **go2china**，Web 品牌仍为 **go2china.space**。素材文件名中的 RoamLion 保留素材来源语义，不代表产品改名。

| 仓库文件 | 用户上传原名 | 实际格式与尺寸 | 字节数 |
| --- | --- | --- | ---: |
| [roamlion-symbol-original.png](roamlion-symbol-original.png) | `RoamLion_Symbol_4K(2).png` | PNG，2048 × 2048 像素 | 4,183,637 |
| [roamlion-symbol-original.svg](roamlion-symbol-original.svg) | `RoamLion_Symbol_4K(2).svg` | SVG，4096 × 4096 画布；内嵌 PNG 为 1951 × 1792 像素 | 5,819,001 |

SVG 实际是一个嵌入位图的容器，仅含 `svg/title/desc/image` 元素，没有矢量路径；不能据其扩展名或画布尺寸宣称可无限放大。内嵌 PNG 与单独上传的 PNG 是不同字节内容。SVG 服务 MIME 为 `application/octet-stream`，实际静态检测为 `image/svg+xml`；PNG 服务与实际 MIME 均为 `image/png`。

## 完整性与静态检查

两份文件均逐字节保留用户上传原件。只静态读取 XML 与 PNG 结构，没有执行 SVG、加载外部资源或渲染转换。SVG 未发现脚本、事件处理器、外部引用、DOCTYPE 或实体声明；独立 PNG 与内嵌 PNG 均通过块 CRC、压缩流及无尾随数据检查。独立 PNG 只有 IHDR/IDAT/IEND 块，无附带文本或其他元数据块。SVG 文本仅为素材标题和说明，未发现凭据文本。

SHA-256：

```text
cc1460d9ae4e46424289b5fd18c79d37361c2f536686090ae5774988b05670b1  roamlion-symbol-original.png
692150e8434924c9b82927307fb244a1f162ced70961fb886a5dd2a3cdc277af  roamlion-symbol-original.svg
```

在本目录运行 `shasum -a 256 roamlion-symbol-original.png roamlion-symbol-original.svg` 可核对原件。详细尺寸、MIME、内嵌位图哈希和静态检查结果见 [manifest.json](manifest.json)。

## 权利说明

用户授权将本次指定原件保存到此公开仓库。未提供素材许可文本；本归档不授予或宣称任何开源许可，也不推定第三方使用权。
