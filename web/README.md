# go2china.space 网页

G2C 官网落地页：介绍 CJ Agent 和 App 里已上线的工具，推荐 App，唯一 CTA 为 `Apply Early Access`（所有语言固定使用该文案）。纯静态页面加一个 Vercel Function，无构建步骤、无前端依赖。改页面前先读 [DESIGN.md](DESIGN.md)。

- `index.html` — 页面结构
- `styles.css` — 样式（字体自托管，见 `assets/fonts/`）
- `i18n.js` — 六种语言文案（英、简中、俄、西、阿、法），含聊天演示、工具清单、照片墙地名、表单选项。整页只写已上线的能力（#1839）：脱敏、JT Agent 后台跟进、工单与真人同事接手的承诺和演示已撤下，每项上线后再写回
- `app.js` — 渲染与交互：聊天演示（预设问题打字/删除，仅动效）、照片墙轮换、报名表单
- `api/early-access.js` — 报名接口：校验后经 Jotform 官方 API 写入现有 Jotform 表单
- `service-request.js`、`api/service-request.js`、`api/_service-request-destination.js` — 广州中英商务陪同的申请表与接口（#1777），开关默认关，见下文「服务申请入口」
- `credits.html`、`assets/sights/CREDITS.md` — 景点照片作者与许可（CC BY / BY-SA 需署名，勿删）
- `assets/` — LOGO、吉祥物、景点照片、字体

## 本地预览

```bash
python3 -m http.server 8080 --directory web
```

静态预览下 `/api/early-access` 不可用，提交会显示失败提示和备用表单链接；完整流程以 Vercel Preview 为准。

报名接口离线回归检查：`node --test scripts/test_web_early_access.cjs`；服务申请入口：`node --test scripts/test_web_service_request.cjs`（都在仓库根目录运行）。

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

## 服务申请入口（#1777，默认关）

申请一位广州的中英商务陪同：称呼、邮箱、日期、说明（选填，提示简单说需要什么帮助、时间地点由我们邮件确认、不要填证件号和健康信息），以及四个必勾的勾选框：已阅读隐私政策，和三项分项同意（行踪信息、提供给陪同人员、数据出境到香港；PIPIA 增补 13.4），每项链接到隐私政策对应段落（`/privacy#website-requests`、`#in-person-services`、`#cross-border`，锚点待合规文档线在政策里补上）。四项缺任一项，页面拦下，服务器返回 400。城市固定广州，服务只有「中英商务陪同」一项，城市由服务器写入，不由浏览器提交。页面写明通常在 1 个工作日内（北京时间）从 hello@go2china.space 邮件回复（JT 2026-11-26 定）；这个地址在回复说明、提交成功和失败提示里都以可选中的普通文字显示，不只做成 mailto 链接。不经过 Jotform。服务器校验与报名接口一致：超出长度上限的文字截断到上限，请求体超过 16 KB 拒绝（413）。

开关打开时有两个入口：顶部导航（窄屏随导航一起隐藏）和首屏文字下方的链接（所有屏宽可见），都跳到表单区块。

开关是仓库常量 `SERVICE_REQUEST_ENABLED`，页面（`service-request.js`）和函数（`api/service-request.js`）各有一份，离线测试检查两者一致。不用 Vercel 后台设置。关着时：

- `service-request.js` 第一行就返回：页面没有表单，顶部导航和首屏文字下方都没有入口链接，不发任何请求。`index.html` 里只有这个脚本的 `<script>` 标签，`app.js` 不知道这个入口的存在（语言由 `service-request.js` 自己跟随语言选择框）。
- `/api/service-request` 对任何请求返回 404，不读请求体，不记日志，不转发。

申请经 `api/_service-request-destination.js` 的「去向」送出（下划线开头，Vercel 不把它当作单独的函数）。现在只有一个只写日志的替身 `LOG_ONLY`：只记字段长度和是否填了日期，不记称呼、邮箱、日期和说明原文，也不记由它们算出的哈希。开关打开而去向仍是 `LOG_ONLY` 时离线测试失败。

打开开关前须全部满足（打开时只改两处常量，并把去向换成真实实现）：

1. 隐私政策（草稿 `docs/privacy/privacy-policy.md`）已在官网 `/privacy` 公开。表单里的隐私政策链接指向 `/privacy`，现在这个页面还不存在。隐私政策首次公开须 JT 本人确认。
2. `DEFAULT_DESTINATION` 换成服务线的服务请求后端（W9，契约 #1768）。
3. 统筹指定收件人，并有一条测试申请到达人工（#32）。

## 图片

`assets/sights/` 共 36 张景点照片，来自 rawpixel（CC0）与 Flickr（CC BY 2.0 / CC BY-SA 2.0），经 Openverse 检索，仅缩放并转为 WebP。页脚“Photo credits”链接到 `credits.html` 列出作者与许可。新增照片须补充署名。

## Logo 来源

`assets/g2c-logo.png` 与 `ios/Branding/Assets/BrandAvatar.png` 逐字节一致（SHA-256 `dc2ca11638328f658669c21d5ff5d24010ee70f5f704f46354b09334e1560f4d`），来源为 `digital-assets/ios-avatar/2026-10-21/roamlion-symbol-original.png`，对应关系见 `ios/Branding/source-and-derived.json`。原始数字资产未修改。

## 字体

Onest（拉丁、西里尔）与 IBM Plex Sans Arabic 来自 Fontsource，均为 SIL Open Font License 1.1，许可证见 `assets/fonts/`。中文使用系统字体。
