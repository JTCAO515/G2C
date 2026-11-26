# go2china.space 网页

G2C 官网落地页：介绍 CJ Agent 和 App 里已上线的工具，推荐 App，唯一 CTA 为 `Apply Early Access`（所有语言固定使用该文案）。纯静态页面加一个 Vercel Function，无构建步骤、无前端依赖。改页面前先读 [DESIGN.md](DESIGN.md)。

- `index.html` — 页面结构
- `styles.css` — 样式（字体自托管，见 `assets/fonts/`）
- `i18n.js` — 六种语言文案（英、简中、俄、西、阿、法），含聊天演示、工具清单、照片墙地名、表单选项。整页只写已上线的能力（#1839）：脱敏、JT Agent 后台跟进、工单与真人同事接手的承诺和演示已撤下，每项上线后再写回
- `app.js` — 渲染与交互：聊天演示（预设问题打字/删除，仅动效）、照片墙轮换、报名表单
- `api/early-access.js` — 报名接口：校验后经 Jotform 官方 API 写入现有 Jotform 表单
- `credits.html`、`assets/sights/CREDITS.md` — 景点照片作者与许可（CC BY / BY-SA 需署名，勿删）
- `assets/` — LOGO、吉祥物、景点照片、字体

## 本地预览

```bash
python3 -m http.server 8080 --directory web
```

静态预览下 `/api/early-access` 不可用，提交会显示失败提示和备用表单链接；完整流程以 Vercel Preview 为准。

报名接口离线回归检查：`node --test scripts/test_web_early_access.cjs`（在仓库根目录运行）。

## Vercel

Root Directory 设为 `web`，Framework Preset 选 Other，Build Command 与 Output Directory 留空。`api/` 下的文件自动成为 Vercel Function（Node.js）。`vercel.json` 设置缓存与安全响应头，以及跳过构建的判断 `ignoreCommand`。

只在 `web/` 变化时部署（#1719）：`ignoreCommand` 在 `web/` 目录里比较本次提交与该分支上次成功部署（`VERCEL_GIT_PREVIOUS_SHA`）之间 `web/` 有没有变化，没变化就跳过构建。上次部署的提交不在 Vercel 的浅克隆里时，生产部署改为比较合并提交与它的第一个父提交（即整个 PR 的改动）；预览部署拿不到可比较的提交时照常构建。命令出错一律构建，不会漏部署。它会覆盖 Vercel 项目设置里的 Ignored Build Step，所以要改跳过规则就改这里。离线检查：`python3 -B -m unittest -v scripts.test_web_vercel_ignore`（`scripts/test.py` 会跑）。

需要在 Vercel 项目 Settings → Environment Variables 配置（Production 与 Preview）：

| 变量 | 必填 | 说明 |
|---|---|---|
| `JOTFORM_API_KEY` | 是 | Jotform → My Account → API → Create New Key，权限选 Full Access。只放在 Vercel，不入库 |
| `JOTFORM_FORM_ID` | 否 | 默认 `263094082842055`（当前报名表） |
| `JOTFORM_API_BASE` | 否 | 允许 `https://api.jotform.com`（默认）、`https://eu-api.jotform.com`、`https://hipaa-api.jotform.com` |

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

## 隐私政策页（`/privacy`）

- `privacy.html` 由 `scripts/build_privacy_page.cjs` 从 `docs/privacy/privacy-policy.md` 生成，不手改。改政策后在仓库根目录运行 `node scripts/build_privacy_page.cjs`；`--check` 检查页面是否与政策一致，`--strict` 另外要求没有【待…】、`[JT: …]` 这类占位符，也没有下面列出的拆分或锚点问题（公开前用）。离线测试：`node --test scripts/test_web_privacy_page.cjs`（页面与政策不一致就失败）。
- 政策是中英双语（每节先中文后英文）。生成时按有没有汉字把段落、列表项分到中文和英文两份；写成「中文 / English」一行的标题、表格单元格、段落和列表项按斜杠拆成中英两条（斜杠后面要有空格，代码里的路径不算）。拆不开、仍然中英混排的行会报出原文，`--strict` 失败。Markdown 里的 HTML 注释是起草说明，不上页面；H1 由页面标题代替。
- 页面只出中文和英文：网站语言选中文时显示中文，其他语言显示英文；选俄、西、法、阿语时页面写明政策只有中英文版本（`privacy.js`，文案在 `i18n.js` 的 `privacyPage`）。
- 锚点只认政策里写的：标题、段落或列表项行尾的 ` {#锚点名}`。双语标题写一次，中英两份都有；段落和列表项要在中文和英文那条各写一次。服务申请表（#1862）链接的 `#website-requests`、`#in-person-services`、`#cross-border` 缺任何一个，或者只在一种语言里有、在同一种语言里出现两次，都会报出来，`--strict` 失败。页面上只有当前显示的那份带 `id`（切换语言时脚本把 `id` 移过去，页面加载完再跳一次），所以选中文或英文时 `/privacy#cross-border` 都能跳到对应段落。
- 页脚有「隐私政策」链接（`/privacy`，`cleanUrls` 会把它对应到 `privacy.html`）。

## Early Access 的中国大陆以外处理同意

报名表在提交按钮上方写明「提交即表示你已阅读隐私政策，你的申请会由 Jotform（美国）处理」，并加一个必勾的勾选框「我同意传到中国大陆以外（中国香港和美国）处理」（统筹 2026-11-26 定）。不勾时页面拦下；服务端 `api/early-access.js` 要求 `consentAbroad === true`，否则返回 400 `consent_required`，不转发 Jotform。Jotform 表单里没有对应题目，所以这个同意只在服务端校验，不写进 Jotform。
