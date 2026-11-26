# 场景包与开关（#1737，ADR-0010）

「场景包」是任务所属领域（旅游 `travel`、商务 `business`），不是对话阶段 `Scene`（`lio_exploration_policy`）。
格式由 S 线定，其他票只通过 `cj_api.scene_pack_config` 读取，不改格式。

- `travel.json`、`business.json`（`g2c-scene-pack.1`）：`title`、`languages`（固定 en、zh）、`cities`（空表示不按城市开关）、
  `knowledge`（`id`、https `source`、`verified_on`、`review_by`）、`tools`（App 工具注册表 #1724 的 id，只引用不新建）、
  `flows`（步骤模板，中英）、`risk_rules`（不能说、不能做的事，至少一条）、`commitments`（能承诺到哪一步、凭据，至少一条）。
- `switches.json`（`g2c-scene-switches.1`）：每个场景包、每个场景包的每个城市、真人入口 `human_service`、收款 `payments`、
  就医 `medical` 各一个开关。新增开关一律从关开始；从关改开要单独的已审 PR，并写明统筹的决定出处。
- 旅游保持开启，行为与构建 57 一致；商务要场景包开关和城市开关同时打开才生效。
- 未知键、重复键、未知工具或城市、缺中文或英文都直接报错（失败即关闭）。
- 目前运行时还没有模块读取场景包（测试会检查），W2-8 #1738 接入时再改该测试。
