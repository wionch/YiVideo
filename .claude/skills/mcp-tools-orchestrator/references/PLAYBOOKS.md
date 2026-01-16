# references/PLAYBOOKS.md

# 编排剧本（Playbooks）

## P0：重构/排障（仓库为主）

1. （复杂任务）sequential-thinking：拆解子问题、列假设、给出工具链与退出条件
2. serena：定位符号/入口/调用链/引用面，收敛到具体文件与函数
3. （如涉及第三方库/框架）context7：resolve + docs，明确版本前提
4. （如需外部对照）brave-search：广覆盖找官方/权威线索
5. （brave 噪声大或需研究级证据）exa：精筛、补齐代码证据/论文/权威报告
6. （需要原文证据或字段化）tavily-remote：抽取关键 URL（记录日期/版本/原文位置）
7. 输出：最小 diff/改动点 + 回归验证步骤 + 风险点

## P1：查最新用法（文档为主）

1. context7：resolve library id
2. context7：get docs（按“当前任务主题”检索，不要泛搜）
3. （如需迁移/变更背景）brave-search / exa：找官方公告/迁移指南并交叉验证
4. （需要引用原文）tavily-remote：抽取关键段落（含版本/日期）
5. 输出：版本前提 + 示例代码 + 常见坑 + 验证步骤（单元测试/最小复现）

## P2：Web 研究与抽取（证据链为主）

1. brave-search：广覆盖发现候选来源（先官方/规范/权威机构）
2. exa：高精度精筛（尤其是代码证据、研究级材料、主仓库）
3. tavily-remote：对关键 URL 做 extract；站点规模大则 map/crawl
4. 交叉验证：时间敏感/高风险结论至少两来源互证
5. 输出：结构化摘要（要点 + 日期 + 版本号 + 原文证据位置）
