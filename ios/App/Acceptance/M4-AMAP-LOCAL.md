# M4 高德本地开发配置（#398）

此配置仅供 M4 授权条目 1、2 的指定 iPhone 开发测试。普通工程、CI、
模拟器及 Release/Production 不依赖高德库或 Key；MapKit 保留。JT 当前要求
先跳过真机，待连接通知后才签名、安装和执行下述真机步骤。

SDK 许可与隐私条款版本/生效日期目前 UNKNOWN；Part 2 首次载入前须从官方材料
核实并记录版本和日期，再同步 #34/#225。本地编译不表示已完成许可或隐私验收。

## SDK 与无秘密编译

从[高德官方 SDK 下载页](https://lbs.amap.com/api/ios-sdk/download/)取得下列两个
固定归档，在仓库外分别命名为 `map-11.3.100.zip` 与
`foundation-noidfa-1.9.4.zip`。不将库、归档或运行证据提交 Git。

| 官方归档 | SHA-256 |
|---|---|
| [3DMap 11.3.100](https://a.amap.com/lbs/static/zip/AMap_iOS_3DMap_Lib_V11.3.100.zip) | `231fedcd79532932864a9b39717164cb6a3267bf53dc5d755bf9894ebba04af7` |
| [Foundation NO-IDFA 1.9.4](https://a.amap.com/lbs/static/zip/AMap_iOS_Foundation_NO_IDFA_Lib_V1.9.4.zip) | `e812db2c83e2542e8bcd1d6904e03d49fa1a2e20b33772e1c3f1ede14d5dd552` |

```sh
python3 -B ios/App/Acceptance/prepare_m4_amap.py --sdk-cache '<external-sdk-cache>'
xcodebuild -project ios/.local-amap-device/AMapLocal.xcodeproj -scheme AMapLocal \
  -configuration Debug -xcconfig ios/.local-amap-device/AMap.xcconfig \
  -destination 'generic/platform=iOS' -derivedDataPath '<external-build-directory>' \
  -skipPackageUpdates -onlyUsePackageVersionsFromResolvedFile CODE_SIGNING_ALLOWED=NO build
```

生成器只写 Git 忽略的 `ios/.local-amap-device/`，检查归档哈希、路径边界并补模块
声明；不改 SDK 二进制。它保留已有本地构建，重新生成前先把该忽略目录移到仓库外。
无 Key 编译仍链接官方 iPhoneOS arm64 SDK，但 UI 明示高德未配置并使用 MapKit。
编译不创建地图，不证明底图、标注、隐私时序、SDK 网络行为或真机运行。

## Key、构建身份与签名

收到连接通知后，核对 main 上 M4 条目 1、2 仍有效，再在全新忽略目录生成时加
`--inject-key`。该参数只从钥匙串 `g2c-amap-ios-key` 读入 Key，写入权限 0600 的
本地 `AMapLocalKey.plist` 并作为本地 Debug 资源复制；不打印 Key，不把它放进
命令参数、环境变量、构建设置、日志或 PR。设备上的开发包因此含 SDK 所需 Key，
只能留在获准设备，不分发。删除本地配置/卸载该开发包即撤销此本地注入。

高德 Key 绑定 `space.go2china.app`，所以本地 AMap 工程的 **Debug** 单独使用此
Bundle ID；加载资源时再次核对该 ID。主工程 Debug 的
`space.go2china.foundation.local` 和各 `*.acceptance` ID 保持隔离，不复制该 Key。
本地工程只提供 Debug 配置；此构建不是正式发布包。普通 Production 虽有同一
正式 ID，也不含 Key 或高德依赖。签名默认关闭；指定团队及自动开发签名仅在
获准的本地配置启用，证书/profile 不导出、不入库，不上传 TestFlight 或商店。

## 本机后端与数据边界

本地 xcconfig 显式定义 `G2C_M4_DEVICE_ACCEPTANCE` 与 `G2C_AMAP_LOCAL`。
运行时设置 `G2C_M4_LOCAL_HOST` 为开发机的规范点分十进制私网 IPv4；已有
`G2C_DEV_*_URL` 使用完全相同 host 的 `https://<host>:<port>`。配置必须提供端口，
不得含凭据、路径、查询或片段；DNS、公网与其他 host 均拒绝。设备配置也拒绝
手机自己的 loopback；原 loopback HTTP 只供 Mac/模拟器。跨主机 HTTP 拒绝；
本地 API 必须提供设备系统信任、地址匹配且有效的 TLS 证书，沿用 URLSession
默认校验，不接受自签名旁路或信任回调。当前 TLS 启动与设备信任尚未验收。未定义设备编译
标志时仍只接受原 loopback。仅 Debug 含本地网络 ATS 与用途说明，其他配置删除
两者；不申请定位权限。真实签名 API/受限 PG/FakeProvider 的启动配置沿用已有
验收驱动，设备可达监听与访问控制需在实际执行时核实，不能冒称已跑通。

保留签名 token、当前 session/owner、每条路由/版本/原动作校验、请求/响应上限和
禁止重定向。此配置不新增 HTTPS 测试域名业务写权限；等 B 在 #30 通知测试域名
就绪，再接 `https://api-beta.go2china.space` 并单独复验。

## 地图与验收记录

先展示来源、原 provider ID、原 GCJ-02 字符串及文字行程。只有点开地图、阅读
SDK 数据处理说明并明确「同意并加载高德地图」后，才报告 SDK 隐私同意并创建
地图。关闭可选分析，不请求定位，不启用搜索/路线/定位服务。非 GCJ-02 不画点，
无 Key 回到 MapKit，加载失败保留文字和错误提示。原坐标仅作 Decimal→Double
呈现，不转换坐标系；英文官方名称缺失仍保留 UNKNOWN，不自行翻译来源记录。

真机须分别记录中英底图标注与语言切换、provider ID/坐标一致、未同意时无地图、
失败时完整文字、最大字号及 VoiceOver。`trip.map.amap` 的成功加载值包含本进程
地图创建序号；它不是瓦片 HTTP 请求数。记录地图实际创建/加载次数、其他服务
调用及费用；SDK 内部瓦片请求数不可观测时记 UNKNOWN。截图/录屏不含 Key。
SDK 处理查看区域及设备/网络信息的核对结果同步 #34/#225，授权使用记录由文档
owner 更新 M4.md。本轮无 Key、无签名编译：地图创建 0、其他高德服务 0、费用 0；
真机、地图网络行为与中英标注 UNRUN。使用 [DEVICE-RECORD](DEVICE-RECORD.md)
填写实际结果，历史 FAIL 保留。
