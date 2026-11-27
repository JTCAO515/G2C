# 香港发布工具（deploy/release-tools）

香港 beta 的发布链脚本（#1950）。以前这些脚本只放在开发机的 `~/.local/share/g2c/b-server-smoke-20261118/`，没有版本管理。现在代码放在仓库里，改动一律走 PR，**按红线审查**。

## 代码和状态分开

- **代码**：本目录。脚本之间按仓库里的相对路径互相调用（`CODE = Path(__file__).parent`）。以前各脚本运行时会互相核对 sha256，现在去掉了，改由 PR 审查来保证代码正确。
- **状态**：都在仓库外，由环境变量 `G2C_RELEASE_STATE` 指定，默认是 `~/.local/share/g2c/b-server-smoke-20261118`。包括：
  - gate：`<run>-forward-gate.json`；
  - 证据：`release-*-evidence.json`、`*-hk-identity.json`、`*-image-proof.stdout`；
  - 每一步的 stdout 和 stderr；
  - ABI 策略副本：`policy-*.json`；
  - C 会话令牌：`c-20261119-zh.jwt`；
  - 翻译冒烟夹具：`translation-supplement-20261123-fixtures/`。
- **状态目录的同级目录**（`$G2C_RELEASE_STATE/..`）：
  - `b1048-m1-deploy-20261116/`：G2C 组合成测试邀请 `A1124-198-shortcode-samples-20261117/group-g2c.invite`，以及回滚驱动 `app-release-idle55-compat3-gatebytes-20261117.py`；
  - `b759-national-20261112-03/zh.jwt`：旧冒烟入口用的 C 会话。
- **不进仓库的东西**：令牌、邀请码、样本凭据、发布证据、日志和主机数据。仓库里只记它们的路径约定。私有文件的权限必须是 600，脚本会拒绝软链接。
- 本机副本和「禁止清理」说明放在 `~/.local/share/g2c/keep/`。**`~/.local/share/g2c/` 下的东西任何线都不能清理**：2026-11-27，清理脚本删掉了 b1048，当晚的发布因此中止。
- SSH 私钥默认是 `~/.ssh/g2c-beta.pem`，可以用 `G2C_RELEASE_SSH_KEY` 改。

## 怎么运行

- 当前目录必须是**发布源的精确检出**，并且干净（脚本会断言 `git rev-parse HEAD == 源`）。脚本用绝对路径调用本目录里的文件：
  ```
  cd <worktree at S>
  python3 -B <这份仓库检出>/deploy/release-tools/s-build53-batch-stage.py stage-permanent $S $P $R
  ```
- 要导入仓库模块的脚本，用发布源的环境去跑：
  ```
  env -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY -u http_proxy -u https_proxy -u no_proxy -u ALL_PROXY -u all_proxy \
    sh -c "export PYTHONPATH=.:scripts:backend; uv run --offline --locked python -B <tools>/x.py ..."
  ```
  这类脚本包括 pre-cutover、batch smoke、drain、quick-restore、s55、verify。
- 所有命令都在沙箱外运行，因为要用到 SSH 和本机状态目录。

## 普通应用发布（L 发布，schema 不变）的顺序

| 步骤 | 命令 | 前置条件 |
|---|---|---|
| 1 verify local | `s54-release-verify.py local $S <主 PR>` | 源提交首轮 CI 全绿；范围内每个 PR 的精确 head 都有 `Review: APPROVE`；ABI 策略已换代（见下）。 |
| 2 hk-verify | `s54-release-verify.py hk-verify $S <主 PR>` | 镜像已用 `deploy.hk.build --platform linux/amd64` 构建，并通过 `docker save \| gzip \| ssh 'gunzip \| docker load'` 传到香港；本机和香港的 config、layers 一致。 |
| 3 stage-permanent | `s-build53-batch-stage.py stage-permanent $S $P $R` | 香港上 `probes/$R` 必须还不存在：每个 run 号只能用一次。 |
| 4 write-gate | `s-build53-batch-stage.py write-gate $S $P $R` | 窗口 29 分钟，从写入时刻算起；香港端用 `xb` 方式写入，**只能写一次**。要在 apply 前约 8 分钟写，让窗口盖住 apply 之后的读回和冒烟。 |
| 5 pre-cutover | `s-build52-pre-cutover-preflight.py $R` | 在旧服务上用 C 会话和 G2C 组合成会话各登录一次，provider 调用为 0；需要上面的邀请码文件。 |
| 6 apply | `python3 -I -B s54-release-transport.py apply $S <launcher sha256> $R`（GH_HOST=github.com） | **不能重跑**。失败就保持现状，对账后换新的 run 号。 |
| 7 readback | `s-build53-batch-stage.py readback $S $P $R` | |
| 8 batch smoke | `s-build53-batch-smoke.py $R` | 窗口剩余不到 145 秒时，改用 `s-build53-batch-smoke-late.py`。 |
| 9 drain | `s-build52-drain.py $R drain $S <新镜像 ID>` | |
| 10 quick-restore | `s-build52-quick-restore.py $R` | |
| 11 s55 功能冒烟 | `s55-smoke.py $R taxi\|nearby\|english` | |

读回检查：`cj_ops_console` 是 NOLOGIN；jt-workbench 是 healthy；告警 check 为 0；GC 日志正常。

## schema 升级（一次只升一级）

`deploy/hk/demo_schema.upgrade` 要求镜像的迁移正好是 `1..target`，库里是 `1..target-1`。所以**一个镜像只能带一个新迁移**，每升一级就单独发一次。

- `step-release-program.py`：每次发布填好 `SOURCE`、`OLD`、`OLD_OPERATOR`、`FROM`、`TARGET`、`ADDED_COLUMNS`，按红线送审后使用。它在香港运行。
- 不带 `--apply` 是只读 preflight，期望输出 `STEPnn_PREFLIGHT_PASS`。
- 带 `--apply` 才切换，期望输出 `STEPnn_CUTOVER_PASS`，同样不能重跑。
- `step-gate.sh` 和 `step-ledger.sh` 是 gate 和账本锚点的模板，每次发布要改目录名和镜像 ID。
- gate 的时间必须写成 `2026-11-27T17:00:00.000000+00:00` 这种格式，写成 `Z` 结尾会报 `ValueError`。
- 回滚：先跑 `--check-rollback <target>`。新表里有一行数据就停下，转 JT。

## ABI 策略换代

每次换源都要做：

1. `make-abi-policy.py`：把 `PREVIOUS`、`PREVIOUS_SHA` 指向现役策略，在源检出里运行，生成 `policy-<现役>-<新源>-<日期>.json`，写到状态目录。
2. `install-reviewed-abi-*.py`：模板。填入新旧策略的哈希、现役源和现役镜像，审查后在发布锁下装到香港，然后读回核对哈希。
3. 把 `s54-release-verify.py` 里的策略文件名和哈希改指新策略，随 PR 送审。

## 已知怪癖

- 新 worktree 第一次 merge 会报 stash failed，重试即可。`c0.source.json` 冲突时取 theirs，再按 source_c0 重新生成。
- 源提交首轮 CI 必须全绿，verify local 会检查。CI 排队时只能等。
- 57 条以上审查时，中继的 GitHub 读请求会超过 256；上限已改为 512。
- 范围内任何一个 PR 缺精确 head 的 APPROVE，香港端 `verify_release_range` 就会拒绝。所以要在 apply 之前先在本机核对一遍范围。
- 包含 #1769 或 #1770 的发布，切换前要先把香港 schema 升到 0056 和 0057。
- C 会话令牌有效期 7 天；过期后发布需要重新走签发授权，由 JT 决定。
- Docker Desktop 重启后要手动拉起来。

## 迁移状态

本目录在 #1950 中从本机原样搬入：先做一次逐字节复制的提交，再在单独的提交里改路径和去掉代码哈希互钉，方便对照审查。下一次香港发布前，本机已审版本仍然有效；正式改用仓库版本跑完整条链，是 #1950 的 L1 验收。
