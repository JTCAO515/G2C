# JT 工作台

工作台在仓库根目录启动。阶段一只使用合成数据，进程监听 `127.0.0.1` 上的 HTTPS。账号、会话、队列复核和审计记录保存在进程内存中，退出后会清空。

## 本地启动

使用仓库锁定的 Python 环境。准备一个本地验证器条目，使用 32 位 Base32 随机密钥、SHA-1、6 位、30 秒周期。启动时在终端隐式输入该密钥、当前验证码和管理员密码。密码至少 12 位。

用已信任且包含 `127.0.0.1` IP SAN 的本地证书，或者生成一张仅用于本次演练的自签证书。

```sh
jt_tls=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1' \
  -keyout "$jt_tls/key.pem" -out "$jt_tls/cert.pem"
uv run --locked python -m jt.workbench --cert "$jt_tls/cert.pem" --key "$jt_tls/key.pem"
```

启动后打开 `https://127.0.0.1:8443/login`。自签证书只用于本次本地会话。绑定会消耗当前验证码，等验证器刷新后再登录。管理员可以从「账号管理」为员工分配角色、停用账号、解锁或授权重绑。创建和重绑会签发一次性设置码，管理员把它当面交给员工本人，员工通过「首次设置或重绑验证器」输入自己的密码和验证器资料。设置码只在签发时显示，有效期 15 分钟。停用、改角色和重绑都会撤销该员工的现有会话。

本地会话最长 60 分钟，连续 15 分钟未使用则过期。单账号连续失败 5 次锁定 15 分钟。整个工作台每分钟接受最多 20 次登录尝试。退出后服务端撤销当前会话。

## 运行测试

```sh
uv run --locked python -B -m pytest -q -p no:cacheprovider jt
```

鉴权测试使用合成账号、固定时间和 [RFC 6238 附录 B](https://www.rfc-editor.org/rfc/rfc6238.html#appendix-B) 的公开向量。审计接口支持追加登录、失败、查看、标注、揭示事件。工作人员查看信号与复核员提交标注、导出评测样本均写入追加审计。字段揭示功能属于后续阶段。

## 使用队列与导出

管理员创建值班处理员或复核员账号后，使用该员工账号登录，在导航中打开「待办队列」。默认加载 `jt.synthetic.generate_dataset(seed=1706)` 的合成信号。队列按级别、响应截止、发现时间和内部顺序字段排列，筛选与详情由服务器渲染。队列时间显示为北京时间。

P0 横幅在打开队列时可见。页面每两秒刷新本机的告警数量，轮询不会延长会话。点击「开启提醒」可启用本地声音和已获权限的浏览器通知，权限不足时仍可看到横幅。

复核员可标注真实级别、误报、漏报与备注，并查看历史。误报样本的真实级别为空。导出按钮下载 `jt-review-samples.json`，使用 `jt-workbench-review-export.v1`。每个已复核信号取最后一条标注，包含信号类型、识别级别、脱敏证据与版本，以及 `review.actual_severity`、`review.false_positive`、`review.missed`、`review.note` 和 UTC 时间。Case 关联只使用 `case_id`，源事件引用、员工账号和内部信号编号均不进入导出。

引擎联调通过 `jt.common.SignalSink` 调用 `MemoryQueue.publish(signal)`。同 ID 同内容的重复交付只入队一次，同 ID 不同内容会拒绝。阶段一的默认种子未建单。
