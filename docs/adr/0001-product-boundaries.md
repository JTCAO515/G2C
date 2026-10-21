# ADR-0001：产品与用户控制边界

- 状态：**accepted**（JT 确认的产品要求；不是技术验收）
- 日期：2026-10-21
- 归属：CJ-001 [#1](https://github.com/JTCAO515/Go2China/issues/1)、CJ-006 [#7](https://github.com/JTCAO515/Go2China/issues/7)、CJ-011 [#12](https://github.com/JTCAO515/Go2China/issues/12)

## 背景与选项

重做需要明确人群、记忆承诺、页面结构和旧数据边界。讨论曾包括三 Tab、延后历史记忆、继承旧系统，以及全新四 Tab 产品。助手的城市、系统版本和收费建议没有自动成为决定。

## 决定

采用[范围](../scope.md)中的已确认要求：App go2china / Web go2china.space / 后端 CJ Agent；外国来华游客，中英同时首发，受邀内测后准备公开首发；助手/行程/插件/记忆四 Tab、账号在记忆内、插件占位；首批完整长记忆和[用户管理](../memory.md)；[Muse 布局](../ui.md)。采用全新账号与数据，不迁移或删除旧数据。

此次授权仅文档准备和文档 PR。准备完成后等待 JT 明确确认才开发。人工托底/运营 Agent 属二三期；定价、法律条款/许可证、城市、最低 iOS 等按待决表保留。

## 取舍

完整记忆增加跨存储一致性、授权、删除与真实测试成本，但不能通过只交 soul.md 或页面来缩减承诺。保留插件/媒体视觉入口需如实显示未开放，避免用户误以为能力已实现。全新数据降低旧系统耦合，但不消除新工程自身的 schema 版本化与后续迁移职责。

## 验证与替换条件

CJ-025/026/028 [#28](https://github.com/JTCAO515/Go2China/issues/28)、[#29](https://github.com/JTCAO515/Go2China/issues/29)、[#32](https://github.com/JTCAO515/Go2China/issues/32)验证实际链路、真机与效果。用户后续明确改变范围时新建/修订决策并同步受影响 Issue/规格；技术组件失败只触发技术替换，不自动削减这些用户承诺。
