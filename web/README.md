# go2china.space 网页

G2C 的官网落地页：功能介绍与 App 推荐，唯一 CTA 为 Join Waitlist。纯静态（HTML/CSS/JS），无构建步骤、无依赖。

- `index.html` — 页面结构（中英双语，右上角切换；首次按浏览器语言自动选择）
- `styles.css` — 样式
- `app.js` — 文案字典、聊天演示动画（预设问题的打字/删除，仅动效，不连接真实问答）、脱敏演示、候补表单
- `assets/` — LOGO 与吉祥物图片（由品牌原图去白底导出）

## 本地预览

```bash
python3 -m http.server 8080 --directory web
```

## Vercel

导入本仓库，Root Directory 设为 `web`，Framework Preset 选 Other，Build Command 留空，Output Directory 留空（即 `web` 本身）。`vercel.json` 只设置缓存与安全响应头。

## 候补名单

所有 Join Waitlist 按钮打开同一个表单弹窗，收集：称呼、邮箱、国家/地区、了解渠道（来源）、出行时间、同行人、想去的地方、最需要的帮助、备注；并自动附带页面语言、`utm_source/medium/campaign` 与 referrer。选项值统一以英文提交，便于汇总。

提交由第三方 [FormSubmit](https://formsubmit.co) 处理（免账号、免密钥），每条报名以表格邮件发到 hello@go2china.space：

1. 上线后第一次提交时，FormSubmit 会向 hello@go2china.space 发一封激活邮件，点击确认后才开始投递。
2. 激活后 FormSubmit 会提供一个随机别名，可把 `app.js` 中 `WAITLIST_ENDPOINT` 的邮箱换成该别名，避免在页面源码暴露邮箱。
3. 需要表格化管理时，可换成 Formspree / Tally / Google Sheets 等：把 `WAITLIST_ENDPOINT` 改为任意接受 JSON POST 且返回 2xx 的 HTTPS 地址即可。

表单含蜜罐字段 `_honey` 防机器人。

## 图片

`assets/sights/` 的景点照片均来自 [rawpixel](https://www.rawpixel.com) 的 CC0 公有领域图片（经 Openverse 检索），已压缩为 WebP；来源见 `assets/sights/CREDITS.md`。
