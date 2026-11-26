# App 开关清单与打包脚本（#1760、#1762）

- `app_flags.json`：App 功能开关的唯一清单。每个开关是一个 build setting（`G2C_*_ENABLED`），在 Beta 配置里填进 `ios/App/Info.plist` 的同名键（`G2C*Enabled`），App 运行时读这个键，只有 `YES` 算打开。`release` 一节是下一次 TestFlight 构建的版本号和打开的开关，发版前由统筹线程改；某个开关在某个构建打开由 JT 决定。
- `build_app.py`：打 TestFlight 包。由构建 57 的发布脚本泛化而来，开关从 `app_flags.json` 读，每个开关都显式传 `YES` 或 `NO`。
- `test_release.py`：离线检查（`scripts/test.py` 会跑）——清单与 Info.plist Beta 分支的键一一对应且顺序一致；Swift 代码里读的每个开关键都在清单里，清单里的每个开关都有代码在读；打包命令、开关核对、发布说明核对、预演不能上传。

新增开关：同一个 PR 里改 `app_flags.json`、`ios/App/Info.plist` 和 Swift 代码，否则 `test_release.py` 失败。

## 打包步骤

在沙箱外运行（xcodebuild 和 git 要写仓库外的目录）。`--record-dir` 放这次构建的命令、日志和核对结果，必须在仓库外。

```bash
python3 tooling/release/build_app.py archive <main 上 push CI 全绿的完整 SHA> --record-dir <记录目录>
python3 tooling/release/build_app.py verify-archive --record-dir <记录目录>
python3 tooling/release/build_app.py export --record-dir <记录目录>
python3 tooling/release/build_app.py verify-ipa --record-dir <记录目录>
python3 tooling/release/build_app.py upload --record-dir <记录目录>   # 只跑一次；已有结果就拒绝
```

- `archive` 先核对源提交的 main push CI 全绿，再用 `git worktree` 在 `--work-dir`（默认 `$TMPDIR/g2c-app-build<N>`）检出源提交，确认干净后按 Beta 配置签名归档。
- `verify-archive` / `verify-ipa` 核对包名、版本、构建号、团队、最低系统、开关值、Beta 标记与 Beta API 地址、地图链接、出口合规与权限说明、App 内发布说明与源码一致，且正好两条：本构建和上一构建（App 只解码两条）；IPA 另核对发布签名、`get-task-allow` 关闭、只限内部测试。
- `archive --rehearsal` 是预演：发布说明的构建号不强制（只记录），`upload` 拒绝。用来在发布说明还没更新时确认脚本能打出下一构建。
