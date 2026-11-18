# 来华旅行知识库浏览页

本目录是 GitHub Pages 的静态页面源码；不在仓库保存第二份事实数据。构建从 `entries/`、`entries-v2/`、`entries-v3/` 和 `names/` 的正式 JSON 生成部署快照，排除 `examples/`、复核记录、日志和原网页。既有校验器负责格式及来源边界；已到期记录允许纳入索引，但界面在北京时间失效日零时起隐藏正文及条件，并保留日期、来源供复核。签证和入境仍只展示库中的官方渠道指引。

```sh
uv run --locked python -B -m unittest discover -s knowledge/visitor/site -p 'test_*.py'
node --test knowledge/visitor/site/test_freshness.mjs
uv run --locked python -B knowledge/visitor/site/build.py /tmp/visitor-pages
```

构建要求事实数据和页面源码已提交，输出必须为空目录，且位于 `knowledge/visitor` 以外；工作中的页面可用 `--allow-dirty` 生成明确标记为未发布的本地预览。输出仅包含 HTML、样式、脚本模块和生成的 `data.json`。生成元数据含仓库提交、事实数据最近修改提交、访客目录最近修改提交、UTC 构建时间；不作为事实核对日期。

页面加载时从本站静态快照读取数据，显示生成时间和数据版本，不依赖 GitHub API 获取条目。页面额外发起一次可选的 GitHub 公开提交查询，将本次发布所用访客目录版本与当前 main 比较：一致、滞后及请求失败/限流造成的未知分别显示；失败不会伪称同步成功或阻止浏览已发布内容。自动发布工作流状态链接和标识另用于发现部署失败；标识不可用时明确提示。所有时间以北京时间计算，到期日从当日零时起失效。浏览器不发送用户搜索内容。

发布工作流须使用提交的精确 main 版本、验证所有输入并只上传上述构建产物；在该版本主线 CI 通过后部署。不能把本地预览、PR CI 或事实库文件的合并当成 Pages 发布成功；上线后应另核公开页面、版本与随新 main 更新的行为。

JT 2026-11-18 单次授权本功能新增 `.github/workflows/visitor-pages.yml`。工作流在相关 PR 上验证生成，在 main 的访客目录或工作流改变后自动构建；部署前等待相同提交的 main `ci` 成功，并核对该快照的访客目录版本仍与 main 一致。只上传生成目录，取消被后续提交替换的旧发布；部署使用 GitHub 内置短期令牌，不新增凭据。发布状态标识来自该工作流；Pages 设置与环境权限需实际配置并回读。
