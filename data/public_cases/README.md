# 公开真实病例资料

本目录只用于比赛演示和软件测试。共 **1 位公开病例患者、3 段改编摘要**，不能称为 3 个独立病例或真实用户测试。

结构化字段登记见 [registry.json](registry.json)；现有 [cases.json](cases.json) 保留为演示脚本的输入数据。登记表中的 `case_id`、来源、许可、改编范围、`occurred_time`、预期行为和限制应与运行证据逐项对应。

来源：[70-year-old Woman with Chest Tightness and Shortness of Breath](https://pmc.ncbi.nlm.nih.gov/articles/PMC12890330/)。作者 Robert E Dunn、Brianna Klucher、Laura J Bontempo、J David Gatz。DOI [10.5811/cpcem.47061](https://doi.org/10.5811/cpcem.47061)，PMCID PMC12890330。抓取核验日期 2026-09-12。

文章许可区原文为：

> © 2025 Dunn et al. This is an open access article distributed in accordance with the terms of the Creative Commons Attribution (CC BY 4.0) License.

许可链接：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。本项目在保留作者署名、出处和许可的条件下，节选并翻译概括 CASE PRESENTATION 的病史描述。改动包括把 70 岁改为 70 多岁、省略地域和其他背景，不提供姓名、联系方式、精确日期或影像。没有复制全文、诊断与治疗方案。

作者称其机构不要求此病例发表取得 IRB 批准或患者同意；这是论文发表说明，不能据此声称患者参加了本项目试验。本项目未接触该患者，也没有取得或使用医院原始病历。

所有输入标记 `source_kind=document`，摘要中“女儿报告”也不能伪装为本项目收到女儿的直接发言。输入记录时间是本次演示导入时间，发生时间保留 `null`，不虚构绝对日期。

**已知覆盖缺口**：第 2 条包含心率 40 次/分钟，本版本地规则未覆盖心率数值，返回 false 不代表医学正常。第 3 条同样不能用于“没危险”的判断。第 1 条会触发胸闷/呼吸困难规则。演示应同时说明关键词范围有限。

普通生活输入和断网输入来自 `data/synthetic/` 及测试文件，明确属于合成测试。不要把合成案例混入本目录冒充真实数据。

原资料及本目录改编部分按 CC BY 4.0 使用；项目代码的使用授权不由此病例许可决定。
