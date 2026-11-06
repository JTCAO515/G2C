# go2china.space 网页

G2C 的官网落地页：功能介绍与 App 推荐，唯一 CTA 为 Apply Early Access。纯静态（HTML/CSS/JS），无构建步骤、无依赖。

- `index.html` — 页面结构（简体中文、英文、俄语、西班牙语、阿拉伯语、法语；右上角选择，首次按浏览器语言选择）
- `styles.css` — 样式
- `app.js` — 文案字典、聊天演示动画（预设问题的打字/删除，仅动效，不连接真实问答）、脱敏演示、候补表单
- `assets/` — LOGO 与吉祥物图片（吉祥物为既有导出图；logo 复用仓库数字资产的既有派生图）

## 本地预览

```bash
python3 -m http.server 8080 --directory web
```

## Vercel

导入本仓库，Root Directory 设为 `web`，Framework Preset 选 Other，Build Command 留空，Output Directory 留空（即 `web` 本身）。`vercel.json` 只设置缓存与安全响应头。

## Early Access 报名

官网所有 `Apply Early Access`（所有页面语言固定使用该文案） 按钮跳转到同一张 [Jotform 中英表单](https://form.jotform.com/263093841129055)，无需填写人登录。表单由 JT 的已连接 Jotform 账号管理；修改入口为 https://www.jotform.com/build/263093841129055 。

- 必填：名字、邮箱（邮箱格式校验）、信息来源。
- 选填：国家或地区、来中国的时间、想去的地方、最需要的帮助、补充留言。
- 报名保存到 Jotform，接收结果以后台记录为准；不依赖 FormSubmit 激活，不自动承诺获得名额或上线日期。
- 网站只链接公开填写页面，不持有 Jotform API key，也不在官网收集或转发填写内容。题目和选项使用中英对照。
- FormSubmit 请求和旧弹窗已移除；当前不附带旧表单的 `travel_party`、UTM 和 referrer 字段。该范围由 JT 本轮“三项必填加选填问题”的替换要求确定。
- Jotform 的大陆直连和海外打开/真实提交须分别实测；当前网络结果不能证明其他网络可用。若访问受限，保留失败并由 JT 决定替代服务，不自动切换域名或服务绕过。

## 页脚语言

公司名、地址和版权主体复用页面语言字典：简体中文页只显示中文，其他语言页使用已登记的英文公司名和地址；联系邮箱始终显示。阿拉伯语页面使用 RTL 排版。页面语言通过 Jotform 的 `language` 查询参数传给同一表单；表单内语言设置须单独配置和验收；MCP 只支持字段编辑，多语言配置需要官方编辑器。

## 图片

`assets/sights/` 的景点照片均来自 [rawpixel](https://www.rawpixel.com) 的 CC0 公有领域图片（经 Openverse 检索），已压缩为 WebP；来源见 `assets/sights/CREDITS.md`。

## Logo 来源

`assets/g2c-logo.png` 与 `ios/Branding/Assets/BrandAvatar.png` 逐字节一致（SHA-256 `dc2ca11638328f658669c21d5ff5d24010ee70f5f704f46354b09334e1560f4d`），来源为 `digital-assets/ios-avatar/2026-10-21/roamlion-symbol-original.png`，对应关系见 `ios/Branding/source-and-derived.json`。导航、页脚、favicon 和 Apple Touch Icon 统一使用该图；原始数字资产未修改。
