# M4 高德本地开发配置（#398）

此配置仅供 M4 授权条目 1、2 的指定 iPhone 开发测试。普通工程、CI、
模拟器及 Release/Production 不依赖高德库或 Key；MapKit 保留。JT 已于
2026-11-04 通知指定 iPhone 已连接并恢复 Goal，可按条目 1、2 执行开发测试。

条款只读登记见 #398：服务协议更新 2025-12-03；隐私政策更新 2026-09-09、
生效 2026-09-16；技术服务使用许可协议页面未列日期，保留 UNKNOWN。
首次载入前复核并同步 #34/#225。登记日期或编译不表示已购买许可或完成隐私验收。

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
本地 API 必须提供地址匹配且有效的 TLS 证书。JT 已在本轮会话另批一套有效期
24 小时的临时本机 TLS 证书/私钥，登记在 #495：私钥仅开发 Mac 的 0600 文件，
公钥只进忽略的 Debug 包，不装全局根证书。设备 Debug 的专用回调须同时匹配
host、端口与完整叶证书 DER，再以 SSL 主机名策略及 SecTrustEvaluateWithError
检查有效期和信任；仅该叶作为锚点，拒绝其他叶、错误地址/端口和过期证书。
其他主机沿用系统默认验证，原路由与重定向门禁保留。未定义设备编译
标志时仍只接受原 loopback。仅 Debug 含本地网络 ATS 与用途说明，其他配置删除
两者；不申请定位权限。真实签名 API/受限 PG/FakeProvider 的启动配置沿用已有
验收驱动，设备可达监听与访问控制需在实际执行时核实，不能冒称已跑通。

保留签名 token、当前 session/owner、每条路由/版本/原动作校验、请求/响应上限和
禁止重定向。此配置不新增 HTTPS 测试域名业务写权限；等 B 在 #30 通知测试域名
就绪，再接 `https://api-beta.go2china.space` 并单独复验。

设备驱动仍复用原签名 API/受限 PG/FakeProvider 的正式来源链。先在仓库外准备
`operator.json`（版本 `G2C-M4-LOCAL-TLS.1`、明确私网 `host`、获准 `team`），同目录
保留 `server.pem`、0600 的 `server.key` 和 `G2CM4LocalServer.cer`。驱动默认不发现
或创建密钥，只消费这份明确配置；控制接口另有每轮临时令牌，未授权请求拒绝。

```sh
CJ_PG_BINDIR='<PostgreSQL-17-bin>' uv run --locked python -B \
  ios/App/Acceptance/check_scoped_messages.py --device '<approved-iPhone-UDID>' \
  --local-tls '<external-directory>/operator.json' --amap-device \
  --case testFormalPlaceMapEnglish --run-context '<explicit-context.json>' \
  --output '<new-external-evidence>' --build-dir '<external-build-cache>'
```

`--device` 与 `--simulator` 互斥，不把旧模拟器 PASS 移算真机。普通模拟器路径不变。
JT 2026-11-05 取消大字号门槛，设备使用系统默认字号；模拟器故障开关不当作真机断网证明。
TLS 单测使用外部公钥路径、SAN 主机和固定有效时刻（`G2C_M4_TLS_TEST_CERT`、
`G2C_M4_TLS_TEST_HOST`、`G2C_M4_TLS_TEST_TIME`），不读取私钥，不固定某台 Mac 的地址。
打包前严格解析仅含单个证书的 PEM，重编码 DER 并与公钥文件全字节一致核对；
只复制已解析的 DER，私钥误标、混合 PEM、附尾或错证书均在安装前拒绝。
构建时将 SDK Key 固定到本轮忽略目录的 0700/0600 快照，打包后核对资源与快照
一致；构建和测试日志使用同一份扫描值，等待解锁期间轮换原配置不影响本轮。
原始 `.xcresult` 只放独立 0700 隔离目录，始终不可直接分享。进程取得终态退出码
后，构建阶段导出 build 文本，test-without-building 阶段导出包含 console 的 action
日志及进程输出并检查凭据；命中或所需日志缺失即 FAIL。中断或超时时导出可为
UNRUN，整轮仍 FAIL。只留脱敏文本/摘要作为导出证据，不把不透明原包或未经核对
的诊断文件标成无秘密。
验收结束移除临时私钥、本地注入资源及本轮设备包，证书到期不得自动重建续期。

## 地图与验收记录

先展示来源、原 provider ID、原 GCJ-02 字符串及文字行程。只有点开地图、阅读
SDK 数据处理说明并明确「同意并加载高德地图」后，才报告 SDK 隐私同意并创建
地图。关闭可选分析，不请求定位，不启用搜索/路线/定位服务。非 GCJ-02 不画点，
无 Key 回到 MapKit，加载失败保留文字和错误提示。原坐标仅作 Decimal→Double
呈现，不转换坐标系；英文官方名称缺失仍保留 UNKNOWN，不自行翻译来源记录。

真机须分别记录中英底图标注与语言切换、provider ID/坐标一致、未同意时无地图、
失败时完整文字、默认字号布局及完整 `.all` AX。`trip.map.amap` 的成功加载值包含本进程
地图创建序号；它不是瓦片 HTTP 请求数。记录地图实际创建/加载次数、其他服务
调用及费用；SDK 内部瓦片请求数不可观测时记 UNKNOWN。截图/录屏不含 Key。
SDK 处理查看区域及设备/网络信息的核对结果同步 #34/#225，授权使用记录由文档
owner 更新 M4.md。本轮无 Key、无签名编译：地图创建 0、其他高德服务 0、费用 0；
真机、地图网络行为与中英标注 UNRUN。使用 [DEVICE-RECORD](DEVICE-RECORD.md)
填写实际结果，历史 FAIL 保留。
