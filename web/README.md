# go2china.space 网页

G2C 官网落地页：介绍 CJ Agent / JT Agent 的分工与协作，推荐 App，唯一 CTA 为 `Apply Early Access`（所有语言固定使用该文案）。纯静态页面加一个 Vercel Function，无构建步骤、无前端依赖。改页面前先读 [DESIGN.md](DESIGN.md)。

- `index.html` — 页面结构
- `styles.css` — 样式（字体自托管，见 `assets/fonts/`）
- `i18n.js` — 六种语言文案（英、简中、俄、西、阿、法），含聊天演示、协作场景、照片墙地名、表单选项
- `app.js` — 渲染与交互：聊天演示（预设问题打字/删除，仅动效）、协作场景切换、照片墙轮换、脱敏演示、报名表单
- `api/early-access.js` — 报名接口：校验后经 Jotform 官方 API 写入现有 Jotform 表单
- `credits.html`、`assets/sights/CREDITS.md` — 景点照片作者与许可（CC BY / BY-SA 需署名，勿删）
- `assets/` — LOGO、吉祥物、景点照片、字体

## 本地预览

```bash
python3 -m http.server 8080 --directory web
```

静态预览下 `/api/early-access` 不可用，提交会显示失败提示和备用表单链接；完整流程以 Vercel Preview 为准。

## Vercel

Root Directory 设为 `web`，Framework Preset 选 Other，Build Command 与 Output Directory 留空。`api/` 下的文件自动成为 Vercel Function（Node.js）。`vercel.json` 只设置缓存与安全响应头。

需要在 Vercel 项目 Settings → Environment Variables 配置（Production 与 Preview）：

| 变量 | 必填 | 说明 |
|---|---|---|
| `JOTFORM_API_KEY` | 是 | Jotform → My Account → API → Create New Key，权限选 Full Access。只放在 Vercel，不入库 |
| `JOTFORM_FORM_ID` | 否 | 默认 `263094082842055`（当前报名表） |
| `JOTFORM_API_BASE` | 否 | 默认 `https://api.jotform.com`；欧盟账号用 `https://eu-api.jotform.com` |

未配置 `JOTFORM_API_KEY` 时接口返回 503，页面提示失败并给出备用 Jotform 链接与邮箱。

## Early Access 报名与中国大陆访问

Jotform 自身的页面在中国大陆经常打不开（Jotform 支持论坛与 GreatFire 均有记录），所以页面不再跳转到 Jotform，而是把表单直接做在官网上：

1. 浏览器只请求 `go2china.space`：表单 POST 到同域的 `/api/early-access`。
2. Vercel Function 在服务器端校验（必填项、邮箱格式、选项白名单、长度上限、蜜罐字段与最短填写时间），再用 Jotform 官方 API（`POST /form/{id}/submissions`）写入原表单。报名记录仍在 Jotform 后台查看。
3. 失败时页面显示错误、备用 Jotform 链接和 hello@go2china.space。

表单字段与 Jotform 题目一一对应（qid：名字 11、邮箱 3、来源 4、国家或地区 5、来华时间 6、目的地 7 含“其他”、需求 8、留言 9）；选项值与 Jotform 中的英文值完全一致，界面按语言显示译文。若在 Jotform 中改题目或选项，须同步修改 `api/early-access.js` 与 `app.js` 中的 `VALUES`。

页面其余资源（字体、图片、脚本）全部来自本域，不请求 Google Fonts 等第三方服务。

## 图片

`assets/sights/` 共 36 张景点照片，来自 rawpixel（CC0）与 Flickr（CC BY 2.0 / CC BY-SA 2.0），经 Openverse 检索，仅缩放并转为 WebP。页脚“Photo credits”链接到 `credits.html` 列出作者与许可。新增照片须补充署名。

## Logo 来源

`assets/g2c-logo.png` 与 `ios/Branding/Assets/BrandAvatar.png` 逐字节一致（SHA-256 `dc2ca11638328f658669c21d5ff5d24010ee70f5f704f46354b09334e1560f4d`），来源为 `digital-assets/ios-avatar/2026-10-21/roamlion-symbol-original.png`，对应关系见 `ios/Branding/source-and-derived.json`。原始数字资产未修改。

## 字体

Onest（拉丁、西里尔）与 IBM Plex Sans Arabic 来自 Fontsource，均为 SIL Open Font License 1.1，许可证见 `assets/fonts/`。中文使用系统字体。
