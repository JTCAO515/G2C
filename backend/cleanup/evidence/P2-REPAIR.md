# P2 receipt 解码族最小返修

差额 base e16b0a3ff9dd54d7cb637c26acdb9b08e01abdf1；仅原 Cleanup 写区。

原独立来源（只读）：
- /Users/jtsm5p/Documents/Codex/2026-10-21/cj-testing/CJ-024-cleanup/REPORT.md
- 同目录 independent_receipt_checks.py、independent-receipt-tests.log

原两 probe 文件逐字复制到 tests/independent_receipt_checks.py，原FAIL log保存在 p2-independent-before.log；原 e16 HOLD 保留，不追认通过。

修复：receipt 先保持 bytes 类型和4096-byte限额，再 strict UTF8 decode，json object_pairs_hook 在所有对象层级拒绝重复key。只解析视图，不重编码原回执；绑定/terminal/同bytes幂等/原invocation恢复逻辑不变。rebuild 仍逐份原bytes通过同一 receipt 校验入口；旧含歧义/错误编码的记录无法恢复为complete。

作者验证（Python3.14、内存合成）：
- 原两独立probe逐字重放2PASS：p2-independent-after.log。
- 3项受影响控制PASS：p2-controls.log；包括8种无效bytes变体均不改operation/journal，rebuild拒绝对应旧invalidstoredreceipt；合法带空白原bytes重建逐字保留，同bytes幂等、异bytes终态冲突保持。
- 原14PASS复用 e16 tests.txt，不重跑无关域。
- git diff --check PASS。

复现：
```sh
PYTHONPATH=backend/auth:backend/cleanup:backend/cleanup/tests /opt/homebrew/bin/python3.14 backend/cleanup/tests/independent_receipt_checks.py
PYTHONPATH=backend/auth:backend/cleanup:backend/cleanup/tests /opt/homebrew/bin/python3.14 -m unittest test_receipt_decode.ReceiptDecodeControls -v
```

无真实删除/DB/权限/publicquery/付费provider/业务数据变更；原真实集成与Issue I仍UNRUN，独立返修Review/Testing待Main路由。
