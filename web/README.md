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

`app.js` 顶部 `WAITLIST_ENDPOINT` 为空时，提交会打开预填好的邮件发往 hello@go2china.space。接入收集服务后，把它设为接受 `POST {email, lang}` 的 HTTPS 地址即可；选用任何外部服务前须按 `docs/authorizations/` 获得授权。
