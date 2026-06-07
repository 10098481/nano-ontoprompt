# nano-ontoprompt v2.0 — 产品需求文档 & 技术架构说明书

> **文档版本**: v1.1 | **日期**: 2026-06-07  
> **定位**: 从「文件上传 → LLM一键提取」的单步工具，升级为「Data Connection → Raw Storage → Pipeline Transform → Curated Dataset → Ontology Mapping」的全链路 Pipeline 平台。  
> **核心参考**: Palantir Foundry 的五阶段数据集成链路与 Ontology 行为层设计，结合开源技术栈落地。

---

## 版本变更摘要

### v1.1 — Logic & Actions 构建机制补充

本版本补充了 Ontology 中 **Logic** 与 **Actions** 的来源、构建流程、产品形态、运行时行为、数据库模型与任务流程。核心调整是：

- 将 Logic 从「LLM 抽取结果」升级为 Ontology 的 **规则层**，来源包括 Pipeline Transform、Ontology Mapping、Schema/质量约束、业务规则与图推导。
- 将 Actions 从「文档中的动作词」升级为 Ontology 的 **可执行行为层**，由 Object Type、Link Type、状态机、业务规则、用户任务与外部写回需求共同生成。
- Pipeline Mapping 路径新增 `Logic Discovery`、`Action Discovery`、`Human Review`、`Publish Logic/Actions` 阶段。
- 新增 Logic / Action Type 的数据模型、运行时校验、自动化触发和 Agent Tool 暴露方式。

---

## 一、现状分析与升级动机

### 1.1 现有系统架构

```
用户上传文件 (PDF/DOCX/XLSX/CSV/...)
       │
       ▼
 MarkItDown 转换为 Markdown
       │
       ▼
  LLM 一次性提取 (extract_ontology)
       │  ┌── entities (实体)
       ├──┤── relations (关系)
       │  ├── logic_rules (逻辑规则)
       │  └── actions (动作)
       ▼
  Cytoscape.js 图谱展示
```

**技术栈**: FastAPI + SQLAlchemy (SQLite/PostgreSQL) + Celery/Redis + React/Vite/Tailwind + Cytoscape.js

### 1.2 核心痛点

| # | 痛点 | 影响 |
|---|------|------|
| 1 | **数据源单一** — 仅支持手动上传文件，无法对接企业系统 | 无法处理生产环境的实时/批量数据流 |
| 2 | **无原始数据保留** — 上传即转换，原始数据仅存储为 `converted_md` 字段 | 无法追溯、无法重处理、无法审计 |
| 3 | **一步到位的黑盒提取** — 所有格式统一走 MarkItDown → LLM prompt，无针对性处理 | 结构化数据(CSV/表格)丢失schema信息；宽表无法拆分；非结构化PDF提取质量不可控 |
| 4 | **不支持增量更新** — 每次提取都是全量操作 | 数据源变更后必须重新全量提取 |
| 5 | **图谱存储受限** — 实体和关系存在关系型数据库中 | 无法进行图遍历查询；大规模图谱性能差；无向量语义检索能力 |
| 6 | **无数据质量闭环** — LLM提取后仅有自动验证，无人工复核流程 | 关键业务场景需要 human-in-the-loop |

### 1.3 升级目标

借鉴 Palantir Foundry 的 "Data Connection → Raw Dataset → Pipeline Transforms → Curated Dataset → Ontology Mapping" 五阶段链路，在 nano-ontoprompt 上落地一个开源版的简化 pipeline，实现：

1. **多源接入** — connector + 手动上传并行
2. **原始数据版本化存储** — raw dataset 与 media set 分层
3. **分路径 transform** — 结构化/半结构化/非结构化三条处理路径
4. **curated dataset + 人工复核** — 提取结果可审查、可修正、可回退
5. **图数据库 + 向量库** — Neo4j 存储本体图谱，ChromaDB 支撑语义检索
6. **增量更新** — 全链路支持 SNAPSHOT / APPEND 两种同步模式

---

## 二、产品设计

### 2.1 全局导航重设计

**现有导航**: Overview | Ontologies | Prompts | Models | Settings

**新导航** (替换原有):

```
 Overview  |  Pipelines  |  Ontologies  |  Models  |  Settings
```

| 一级导航 | 功能定位 | 子页面/Tab |
|---|---|---|
| **Overview** | 全局仪表盘 | 系统统计、最近活动、快捷入口 |
| **Pipelines** | 数据全链路管理（从接入到清洗） | Connections · Datasets · Transforms · Curated Datasets |
| **Ontologies** | 本体构建与探索 | Info · Graph · Entities · Logic · Actions |
| **Models** | LLM 和模型配置 | 模型列表、提示词管理 |
| **Settings** | 系统设置 | 用户管理、规则配置、导出设置 |

> **设计原则**: Pipelines 内聚了整个数据流的四个阶段（接入 → 存储 → 转换 → 清洗），用户在一个模块内完成所有 ETL 工作。Ontologies 聚焦于「从 Curated Dataset 构建并探索本体」，提供两种构建路径：Pipeline Mapping（从 Curated Dataset 映射）和简易 LLM 提取（沿用 v1 的上传文件 + Prompt 直接提取）。各 Tab（Graph/Entities/Logic/Actions）内置搜索功能。Models 独立出来，因为 Pipeline 的多个阶段（VLM提取、LLM结构化、宽表分析）和简易提取都需要选择模型。

### 2.2 Pipelines — 数据全链路管理

Pipelines 是新系统的核心模块，包含四个子页面，对应数据从外部系统到可用数据集的完整流转。

**路由结构**:
```
/pipelines
  /pipelines/connections          # 子Tab: 数据连接
  /pipelines/datasets             # 子Tab: 原始数据集
  /pipelines/transforms           # 子Tab: Transform管道
  /pipelines/curated              # 子Tab: 清洗后数据集
```

**页面布局**:
```
┌─────────────────────────────────────────────────────────────┐
│  Pipelines                                                    │
│  ┌────────────┬────────────┬────────────┬──────────────┐     │
│  │ Connections│  Datasets  │ Transforms │Curated Data  │     │
│  └────────────┴────────────┴────────────┴──────────────┘     │
│                                                               │
│  (子Tab内容区)                                                │
└─────────────────────────────────────────────────────────────┘
```

数据在四个子Tab之间的流向关系：
```
Connections ──同步──→ Datasets ──输入──→ Transforms ──输出──→ Curated Datasets
                                              ↑
                                        Models (选择LLM)
```

#### 2.2.1 Connections — 数据连接

**页面**: `/pipelines/connections`

管理所有数据源连接，包括 Connector 和手动上传。

```
┌─────────────────────────────────────────────────────┐
│  数据连接                               [+ 新建连接]  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ 📁 文件上传  │  │ 🗄️ 数据库   │  │ 🔗 API      │  │
│  │ (拖拽/批量)  │  │ (JDBC/ODBC) │  │ (REST/gRPC) │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                      │
│  已配置的连接:                                        │
│  ┌────────────────────────────────────────────────┐  │
│  │ 🟢 SAP-ERP-生产系统   │ Database │ 每日 08:00  │  │
│  │ 🟢 MySQL-订单库        │ Database │ 每小时同步  │  │
│  │ 🟡 供应商API           │ REST API │ 手动触发    │  │
│  │ ⚪ 手动上传-批次01     │ File     │ -           │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**支持的 Connector 类型** (MVP 范围):

| 类型 | 具体系统 | 连接方式 | 优先级 |
|------|---------|---------|--------|
| **关系型数据库** | MySQL, PostgreSQL | SQLAlchemy 连接池 | P0 |
| **NoSQL** | MongoDB | PyMongo / Motor | P0 |
| **大数据** | Apache Spark (via JDBC/Thrift) | PySpark | P1 |
| **ERP系统** | SAP (RFC/OData), 用友/金蝶 | pyrfc / REST API | P1 |
| **文件上传** | 本地文件拖拽上传 | HTTP multipart (现有功能保留) | P0 |
| **API端点** | 任意 REST API | httpx + JSON Schema | P0 |

**Connector 配置表单字段**:
- 连接名称、连接类型
- 认证信息（加密存储，复用现有 `encryption_service`）
- 同步模式：SNAPSHOT（全量覆盖）/ APPEND（增量追加）
- 同步频率：手动 / Cron 表达式
- 目标 Raw Dataset 名称

**文件上传**（保留并增强）：
- 现有的拖拽上传功能保留，作为 Connection 的一种类型
- 上传后文件进入 **Datasets**（而非直接绑定到 ontology）
- 支持批量上传 + 进度显示
- 自动检测文件类型，分类存储到 Raw Dataset 或 Media Set

#### 2.2.2 Datasets — 原始数据存储

**页面**: `/pipelines/datasets`

对应 Palantir 的 "Git for Data" 概念。展示所有通过 Connection 同步进来的原始数据。

```
┌─────────────────────────────────────────────────────────────┐
│  原始数据集                                 [🔍 搜索数据集]   │
├─────────────────────────────────────────────────────────────┤
│  Raw Datasets (结构化/半结构化):                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 📊 erp_orders_raw     │ 结构化 │ 12,580行 │ v3     │    │
│  │    来源: SAP-ERP-生产系统  │ 最近同步: 2h前           │    │
│  │    [查看数据] [查看Schema] [版本历史]                  │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │ 📋 api_bookings_raw   │ 半结构化(JSON) │ 8,230条   │    │
│  │    来源: 供应商API  │ 最近同步: 30min前                │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  Media Sets (非结构化):                                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 📄 maintenance_reports  │ Document │ 156个文件       │    │
│  │    来源: 手动上传  │ PDF/DOCX                         │    │
│  │    [查看文件列表] [预览] [提取状态]                    │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Raw Dataset 核心功能**:
- **Schema 展示**: 结构化数据自动推断并展示 schema（列名、类型、样本值）
- **数据预览**: 前 100 行预览，支持排序/筛选
- **版本历史**: 每次同步生成一个 transaction（version），可回溯到任意历史版本
- **数据统计**: 行数、列数、null 率、数据类型分布

**Media Set 核心功能**（非结构化文件集合）:
- 文件列表 + 缩略图/预览
- 元数据提取（文件名、大小、页数、MIME 类型）
- 支持的 schema_type: `document`(PDF/DOCX), `spreadsheet`(XLSX/CSV), `image`(PNG/JPG), `audio`, `video`
- 与 Curated Dataset 的 media_reference 关联（提取后的结构化结果可引用原始文件）

#### 2.2.3 Transforms — Transform 管道

**页面**: `/pipelines/transforms`

配置和运行数据转换管道。每条管道从一个 Dataset 出发，经过多步转换，输出到 Curated Dataset。

```
┌─────────────────────────────────────────────────────────────┐
│  Transform 管道                                [+ 新建管道]   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 🔄 erp_orders_pipeline                                │    │
│  │ 输入: erp_orders_raw (结构化)                         │    │
│  │ 路径: Schema Inference → Clean → Split → Output       │    │
│  │ 模型: DeepSeek V4 (宽表拆分分析)                      │    │
│  │ 输出: clean_orders, clean_customers, clean_products   │    │
│  │ 状态: ✅ 最近运行成功 (2h前) │ [运行] [编辑] [日志]   │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │ 🔄 maintenance_extraction_pipeline                    │    │
│  │ 输入: maintenance_reports (Media Set)                  │    │
│  │ 路径: OCR/VLM → Markdown → LLM结构化提取              │    │
│  │ 模型: Claude Sonnet (VLM) + DeepSeek V4 (结构化)      │    │
│  │ 输出: clean_maintenance_records                        │    │
│  │ 状态: 🟡 运行中 (45/156 文件) │ [查看进度] [取消]     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**三条 Transform 路径**:

**路径 A — 结构化数据 (CSV / 数据库表 / Parquet)**

```
Raw Dataset (有 schema)
    │
    ▼  ① Schema 推断 / 确认
    │     - 自动推断列类型 (string / int / float / timestamp / bool)
    │     - 用户可手动修正列类型、重命名列
    │
    ▼  ② 数据清洗
    │     - 去重 (基于主键或全列)
    │     - Null 值处理 (填充默认值 / 删除行 / 标记)
    │     - 格式标准化 (日期格式统一、编码转换)
    │     - 异常行过滤 (jagged rows)
    │
    ▼  ③ 宽表拆分 (可选，关键功能)
    │     - LLM 辅助分析：输入宽表 schema，输出拆分建议
    │       "这张200列的表应该拆分为哪几个实体表？"
    │     - 从 Models 页面选择用于分析的 LLM
    │     - 用户确认拆分方案后，自动生成拆分逻辑
    │     - 每个子表指定主键和外键关系
    │
    ▼  ④ 输出 Curated Dataset(s)
```

**路径 B — 半结构化数据 (JSON / XML)**

```
Raw Dataset (无 schema, JSON/XML 文件)
    │
    ▼  ① 格式解析
    │     - JSON: 自动检测嵌套结构，展示 JSON tree
    │     - XML: 解析 XSD 或自动推断结构
    │
    ▼  ② Flatten (摊平)
    │     - 嵌套对象 → 平铺列 (用 '.' 分隔命名)
    │     - 数组 → explode 为多行 (一对多关系)
    │     - 用户可选择 flatten 深度和策略
    │
    ▼  ③ Schema 确认 + 清洗 (同路径A的②)
    │
    ▼  ④ 输出 → Curated Dataset(s)
```

**路径 C — 非结构化数据 (PDF / DOCX / 图片)**

```
Media Set (document / image)
    │
    ▼  ① 文档提取 (替换现有 MarkItDown 单一路径)
    │     策略选择（需从 Models 选择对应模型）:
    │     ┌─ Traditional: 直接文本提取 (电子PDF) — 无需模型
    │     ├─ OCR: Tesseract/PaddleOCR (扫描件) — 无需模型
    │     ├─ Layout-aware OCR: 保留版面结构 — 无需模型
    │     └─ VLM (视觉语言模型): Claude/GPT-4V 直接"看"文档 — 需选择VLM模型
    │
    ▼  ② Markdown 输出 (每页/每文档一条)
    │     - 带 media_reference 关联原始文件
    │     - 提取质量评估 (自动打分)
    │
    ▼  ③ 结构化字段提取 (LLM pipeline transform)
    │     - 用户定义目标 schema (如: 维修日期、故障描述、更换零件)
    │     - 从 Models 选择 LLM + 选择/编辑提示词
    │     - LLM 从 Markdown 中提取为表格行
    │
    ▼  ④ 输出 → Curated Dataset(s)
```

> **统一输出**: 无论哪条路径，Transform 管道最终都输出 **Curated Dataset(s)**（结构化表格数据）。这是 Pipeline 与 Ontology 模块的唯一衔接点。

**Pipeline 可视化编排**:

- 每个 Pipeline 由有序的 **Transform Steps** 组成
- 每个 Step 是一个预定义操作 (schema_inference / clean / split / flatten / ocr / llm_extract 等)
- 前端用一个线性的步骤卡片列表展示（非自由拖拽 DAG）
- 每个步骤可配置参数，可查看输入/输出预览
- 需要 LLM 的步骤，显示模型选择器（从 Models 页面已配置的模型中选取）

#### 2.2.4 Curated Datasets — 清洗后数据集 + 人工复核

**页面**: `/pipelines/curated`

Pipeline 输出的结果在此展示，供查看和人工复核。这是 Pipeline 模块与 Ontology 模块的衔接点。

```
┌─────────────────────────────────────────────────────────────┐
│  Curated Datasets                            [🔍 搜索]       │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐   │
│  │ ✅ clean_orders      │ 11,240行 │ 已审批 │ 可映射   │   │
│  │ ✅ clean_customers   │ 2,180行  │ 已审批 │ 可映射   │   │
│  │ ✅ clean_products    │ 856行    │ 已审批 │ 可映射   │   │
│  │ ⚠️  clean_maintenance │ 156行   │ 待审核 │          │   │
│  │ 🔄 clean_bookings    │ -       │ 处理中 │          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  点击展开 → clean_orders:                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ [数据预览] [Schema] [质量报告] [人工标注]              │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  order_id │ customer_id │ product  │ amount │ status  │   │
│  │  ORD-001  │ C-100       │ Widget A │ 5,200  │ ✅ 已确认│   │
│  │  ORD-002  │ C-101       │ Part B   │ 1,800  │ ⚠️ 待审 │   │
│  │  ORD-003  │ C-100       │ Widget A │ 5,200  │ ❌ 疑似重│   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  质量报告:                                                    │
│  ├── ✅ Schema 完整性: 所有必填列均有值                      │
│  ├── ⚠️  疑似重复: 23行 (基于 order_id + product 组合)       │
│  └── ℹ️  Null 率: customer_id 2.3%, amount 0%               │
│                                                              │
│  [✅ 批准全部] [⚠️ 标记问题行] [🔄 回退到上一版本]           │
└─────────────────────────────────────────────────────────────┘
```

**人工复核工作流**:
1. Pipeline 输出 Curated Dataset 后，状态为 `pending_review`
2. 用户查看数据预览 + 质量报告
3. 可逐行标注：确认 / 修正 / 删除
4. 批量操作：批准全部 / 标记问题行
5. 审批通过后，状态变为 `approved`，可在 Ontologies 模块中用于映射
6. 修改记录写入独立的 **writeback** 表（不污染原始数据）

### 2.3 Models — LLM 与模型配置

**页面**: `/models`

从 Settings 中独立出来成为一级导航，因为模型是 Pipeline 中多个环节的核心依赖。

```
┌─────────────────────────────────────────────────────────────┐
│  模型管理                                    [+ 添加模型]     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  LLM 模型:                                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 🟢 DeepSeek V4 Flash   │ Compatible  │ 3个模型名     │    │
│  │    用途: 宽表分析、结构化提取、Ontology Mapping        │    │
│  │    [编辑] [测试连接]                                   │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │ 🟢 Anthropic Claude    │ Anthropic   │ 2个模型名     │    │
│  │    用途: VLM文档提取、NL-to-Cypher                    │    │
│  │    [编辑] [测试连接]                                   │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │ 🟢 OpenAI GPT          │ OpenAI      │ 3个模型名     │    │
│  │    用途: 备选通用模型                                  │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  提示词模板:                                                   │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 📝 供应链本体提取   │ v1.2 │ 用于路径C结构化提取      │    │
│  │ 📝 通用宽表分析     │ v1.0 │ 用于路径A宽表拆分        │    │
│  │ 📝 文档OCR提取     │ v1.0 │ 用于路径C VLM提取         │    │
│  │ [+ 新建提示词] [从模板生成]                            │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**核心功能**:
- **沿用 v1 的模型管理**: 保留现有的 Provider/API Key/Base URL/模型名配置（`ModelsPage.tsx` 代码大部分可复用）
- **沿用 v1 的提示词管理**: 保留 Prompt 的创建、编辑、模板生成功能（`PromptListPage.tsx` + `PromptDetailPage.tsx` 可复用）
- **新增用途标签**: 每个模型可标记适用场景（VLM提取 / 结构化提取 / 宽表分析 / Ontology Mapping / NL-to-Cypher）
- **Pipeline 中的引用**: Transforms 配置 LLM 步骤时，直接从这里已配置的模型列表中选择

### 2.4 Ontologies — 本体构建与探索

**页面**: `/ontologies`

Ontologies 模块提供**两种构建路径**，用户可按需选择：

| 路径 | 适用场景 | 数据来源 |
|------|---------|---------|
| **Pipeline Mapping** (新增) | 结构化/半结构化数据，需要精细化 ETL 和人工复核 | Pipeline 输出的已审批 Curated Datasets |
| **简易 LLM 提取** (沿用 v1) | 快速从文档中提取本体，不需要完整 Pipeline | 直接上传文件 + 选择模型/提示词 |

创建完成后，两种路径进入**相同的本体详情页**，共享 Graph / Entities / Logic / Actions 查看和编辑体验。

**路由结构**:
```
/ontologies                              # 本体列表
/ontologies/new                          # 新建本体 (选择构建路径)
/ontologies/{id}                         # 本体详情
  /ontologies/{id}/info                  # 基本信息 + Mapping状态 + 增量更新入口
  /ontologies/{id}/graph                 # 图谱 (Neo4j 渲染，内置搜索)
  /ontologies/{id}/entities              # 实体列表 (内置搜索/过滤)
  /ontologies/{id}/logic                 # 逻辑规则 (内置搜索/过滤)
  /ontologies/{id}/actions               # 动作 (内置搜索/过滤)
  /ontologies/{id}/files                 # 文件 (仅简易LLM提取模式显示，沿用v1)
```

#### 2.4.1 本体列表页

```
┌─────────────────────────────────────────────────────────────┐
│  本体管理                                    [+ 新建本体]     │
│  [🔍 搜索本体...]                                             │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 🧩 供应链知识图谱      │ 供应链 │ 142实体 │ 218关系  │   │
│  │    构建方式: Pipeline Mapping                         │   │
│  │    数据源: clean_orders, clean_customers, clean_products│   │
│  │    状态: ✅ 已同步 │ 最近更新: 1h前                    │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 🧩 合同条款知识库      │ 法律 │ 38实体 │ 52关系      │   │
│  │    构建方式: 简易 LLM 提取                            │   │
│  │    数据源: 3个PDF文件                                 │   │
│  │    状态: ✅ 提取完成                                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### 2.4.2 新建本体 — 双路径选择

**页面**: `/ontologies/new`

```
┌─────────────────────────────────────────────────────────────┐
│  新建本体                                                      │
│                                                               │
│  选择构建方式:                                                 │
│                                                               │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  │
│  │  🔄 Pipeline Mapping    │  │  ⚡ 简易 LLM 提取        │  │
│  │                         │  │                          │  │
│  │  从已审批的 Curated      │  │  上传文件，选择模型和     │  │
│  │  Datasets 映射生成本体   │  │  提示词，LLM 直接提取    │  │
│  │                         │  │                          │  │
│  │  适合: 结构化数据、      │  │  适合: 快速原型、        │  │
│  │  精细化建模、大规模数据  │  │  少量文档、探索性分析     │  │
│  │                         │  │                          │  │
│  │  [选择此方式]            │  │  [选择此方式]            │  │
│  └─────────────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

##### 路径一：Pipeline Mapping

```
Step 1: 基本信息              Step 2: 选择数据源            Step 3: Mapping 配置
┌──────────────────┐        ┌──────────────────┐          ┌──────────────────┐
│ 名称: __________ │        │ 选择 Curated     │          │ Entity Type 映射  │
│ 领域: [供应链 ▼] │   →   │ Datasets:        │    →    │ (LLM自动建议,    │
│ 描述: __________ │        │ ☑ clean_orders   │          │  用户确认/修改)   │
│                  │        │ ☑ clean_customers│          │                  │
│                  │        │ ☑ clean_products │          │ Relation 推断     │
│                  │        │ ☐ clean_maint..  │          │ (FK检测+LLM语义) │
│                  │        │                  │          │                  │
│                  │        │ (仅显示 approved) │          │ [开始构建]        │
└──────────────────┘        └──────────────────┘          └──────────────────┘
```

用户点击「开始构建」后，展示 **Mapping 进度条**：

```
┌─────────────────────────────────────────────────────────────┐
│  Ontology Mapping 进行中                                      │
│                                                               │
│  ████████████████████░░░░░░░░░░  65%                         │
│                                                               │
│  ✅ Entity Type 识别     — 3/3 完成                           │
│  ✅ Property Mapping     — 3/3 完成                           │
│  ✅ Relation 推断        — 7/7 完成                           │
│  🔄 Logic Discovery      — 进行中...                          │
│  ⬜ Action Discovery     — 等待中                             │
│  ⬜ Human Review         — 等待中                             │
│  ⬜ 写入 Neo4j           — 等待中                             │
│  ⬜ 写入 ChromaDB        — 等待中                             │
│  ⬜ 发布 Logic / Actions — 等待中                             │
│                                                               │
│  预计剩余: 约 2 分钟                                          │
└─────────────────────────────────────────────────────────────┘
```

**Mapping 各阶段详细说明**:

| 阶段 | 说明 | 对应 Palantir 概念 |
|------|------|-------------------|
| **① Entity Type 识别** | 每个 Curated Dataset → 一个 Entity Type；LLM 辅助建议中英文名称和描述；用户已在 Step 3 确认 | Object Type |
| **② Property Mapping** | 列名 → 属性名（LLM 辅助翻译和语义化）；列类型 → 属性类型；技术列可隐藏；用户已在 Step 3 确认 | Properties |
| **③ Relation 推断** | 自动检测外键关系（列名匹配 xxx_id）；LLM 辅助推断语义关系；跨数据集关系推断；用户已在 Step 3 确认 cardinality | Link Types |
| **④ Logic Discovery** | 从 Transform 步骤、Schema 约束、质量报告、Mapping 规则、状态字段、图关系和领域 Prompt 中发现候选规则 | Functions / Rules / Derived Properties |
| **⑤ Action Discovery** | 从 Object Type、Link Type、状态流转、人工复核、业务修复和外部写回需求中生成候选 Action Type | Action Types |
| **⑥ Human Review** | 用户审核并确认 Logic / Actions：启用、禁用、调整条件、参数、权限、触发方式和副作用 | Ontology Manager Review |
| **⑦ 写入 Neo4j** | Entity Type → Node Label；每行数据 → Node；每条关系 → Relationship；Logic 可写入规则元节点或独立规则表索引 | Object Graph |
| **⑧ 写入 ChromaDB** | 实体描述、属性、Logic 描述、Action 描述 → 向量嵌入，用于语义搜索和 Agent Tool 选择 | Semantic Search |
| **⑨ 发布 Logic / Actions** | 将审核通过的规则和动作发布为 runtime 可调用定义，供 UI、API、Agent、自动化任务使用 | Kinetic Layer |

#### 2.4.2.1 Logic & Actions 构建机制（新增）

> 设计原则：Entities 和 Relations 是从数据中 **映射** 出来的；Logic 是从 schema、关系、质量约束和业务语义中 **归纳** 出来的；Actions 是从对象状态变化、用户任务和系统写回需求中 **设计** 出来的。

在 v2 中，Logic 与 Actions 不再只是「LLM 一次性抽取」的结果，而是 Ontology Mapping 之后的规则层与行为层。该设计借鉴 Foundry Ontology 中的语义层与行为层拆分：Object Type / Property / Link Type 描述组织中的对象语义，Logic / Action / Function 则描述对象可以如何被校验、推导、修改、审批和写回。

##### A. Logic 的来源

| 来源 | 说明 | 示例 |
|------|------|------|
| **Pipeline Transform Logic** | Transform 步骤本身沉淀的处理逻辑，包括清洗、拆表、flatten、OCR、LLM 结构化提取 schema | `date_format = ISO-8601`、`dedupe by order_id`、`explode flights[]` |
| **Ontology Mapping Logic** | Dataset → Entity Type、Column → Property、FK → Link Type 的映射规则 | `clean_orders.customer_id -> Customer.id` |
| **Schema / Quality Logic** | 从类型、必填字段、枚举、null 率、重复率、异常行中发现的校验规则 | `amount > 0`、`customer_id is required` |
| **Business Rule Logic** | 用户配置或 LLM 根据领域 Prompt 建议的业务规则 | `risk_score >= 0.8 -> high_risk_supplier` |
| **Graph Inference Logic** | 基于图关系和路径推导出的派生关系或派生属性 | `Supplier -> Product -> Order => upstream_supplier_of Customer` |
| **State Logic** | 从状态字段、审核流、生命周期字段中归纳出的状态机 | `pending_review -> approved -> synced` |
| **Security Logic** | 由用户角色、数据集权限、对象类型敏感度推导出的访问和提交限制 | `only admin can approve curated rows` |

##### B. Logic 类型

| Logic 类型 | 运行时用途 | 示例 |
|------------|------------|------|
| **Validation Rule** | 写入前校验、人工复核提示、Action 提交条件 | `Order.amount > 0` |
| **Mapping Rule** | 增量同步、全量重建、血缘追踪 | `Product.sku <- clean_products.sku` |
| **Inference Rule** | 图查询增强、派生关系生成、语义搜索召回 | `SUPPLIES + CONTAINS -> UPSTREAM_OF` |
| **State Rule** | 控制对象状态流转和可执行动作 | `open -> resolved -> closed` |
| **Security Rule** | 控制谁能看、谁能改、谁能执行动作 | `role in ['admin', 'risk_manager']` |
| **Automation Rule** | 条件满足时触发 Action 或后台任务 | `risk_score > 0.8 -> create_review_task` |

##### C. Actions 的来源

Actions 是 Ontology 的可执行行为层，用于把用户决策或系统判断转化为对对象、属性、关系或外部系统的事务性修改。

| 来源 | 生成方式 | 示例 |
|------|----------|------|
| **Object Type** | 每个核心 Entity Type 自动生成基础 CRUD Action，用户可禁用或改名 | `Create Supplier`、`Update Order` |
| **Link Type** | 每个关系类型生成 link / unlink / reassign 动作 | `Link Supplier to Product` |
| **State Logic** | 每条状态流转边生成一个状态迁移动作 | `Submit Review`、`Approve Record` |
| **Validation / Quality Logic** | 为数据质量异常生成修复或复核动作 | `Flag Duplicate Row`、`Fix Missing Customer` |
| **Business Rule** | 为业务判断生成审批、升级、分派、关闭类动作 | `Escalate Supplier Risk` |
| **External Writeback** | 对接外部系统 API、Webhook、ERP、Jira、Slack 等 | `Sync Approved Supplier to ERP` |

##### D. Logic & Actions Discovery 流程

```
Approved Curated Datasets
        │
        ▼
Ontology Mapping
  - Entity Type
  - Property Mapping
  - Link Type
        │
        ▼
Logic Discovery
  - 读取 Transform steps
  - 读取 schema_info / quality_report
  - 读取 mapping rules / FK / cardinality
  - 检测状态字段和生命周期字段
  - LLM 根据领域 Prompt 生成候选业务规则
        │
        ▼
Action Discovery
  - 为 Object Type 生成 CRUD Action
  - 为 Link Type 生成关系维护 Action
  - 为 State Rule 生成状态流转 Action
  - 为 Validation Rule 生成修复 / 复核 Action
  - 为 Automation Rule 生成触发 Action
        │
        ▼
Human Review
  - 用户确认启用/禁用
  - 用户调整参数、权限、提交条件和副作用
        │
        ▼
Publish Runtime Definitions
  - UI 按钮 / 表单
  - API endpoint
  - Agent callable tool
  - Celery automation task
```

##### E. Action Type 定义结构

```json
{
  "name": "Approve Supplier Risk Review",
  "target_object_type": "Supplier",
  "description": "审批供应商风险复核结果，并写入复核日志",
  "parameters": [
    {"name": "supplier_id", "type": "object_ref", "required": true},
    {"name": "review_result", "type": "enum", "values": ["approved", "rejected"]},
    {"name": "comment", "type": "text", "required": false}
  ],
  "submission_criteria": [
    "Supplier.risk_status = 'pending_review'",
    "current_user.role in ['admin', 'risk_manager']"
  ],
  "effects": [
    "set Supplier.risk_status = review_result",
    "create RiskReviewLog",
    "link RiskReviewLog -> Supplier"
  ],
  "side_effects": [
    {"type": "webhook", "target": "risk-system", "condition": "review_result = 'rejected'"}
  ]
}
```

##### F. Runtime 执行语义

1. **用户点击 Action**：前端根据 Action Type 自动生成表单。
2. **提交前校验**：后端执行 `submission_criteria` 与关联 Logic。
3. **事务执行**：在 PostgreSQL 记录 action run，在 Neo4j 中更新对象、属性和关系。
4. **副作用触发**：需要外部系统写回时，通过 Celery 执行 webhook/API 调用。
5. **审计与回滚**：所有参数、执行者、前后值、外部调用结果写入审计表。
6. **Agent 暴露**：发布后的 Action Type 可作为 Agent tool，被自然语言任务调用，但仍受权限和提交条件约束。

##### G. Pipeline Mapping 与简易 LLM 提取的差异

| 构建路径 | Logic 来源 | Actions 来源 | 推荐用途 |
|----------|------------|--------------|----------|
| **Pipeline Mapping** | Transform、Schema、质量报告、Mapping、FK、状态字段、LLM 领域规则 | Object Type、Link Type、State Rule、Validation Rule、外部写回配置 | 生产级、可追溯、可增量更新 |
| **简易 LLM 提取** | LLM 从文档中直接提取候选规则，再由用户修正 | LLM 从文档中提取候选动作，再由用户转成 Action Type | 快速原型、少量文档、探索分析 |

##### 路径二：简易 LLM 提取（沿用 v1）

保留 v1 的核心流程，用户无需经过 Pipeline：

```
Step 1: 基本信息              Step 2: 上传文件              Step 3: 选择模型+提取
┌──────────────────┐        ┌──────────────────┐          ┌──────────────────┐
│ 名称: __________ │        │ 拖拽上传文件:     │          │ 模型: [DeepSeek▼]│
│ 领域: [供应链 ▼] │   →   │ 📄 report.pdf    │    →    │ 提示词: [供应链▼]│
│ 描述: __________ │        │ 📊 data.xlsx     │          │ 提取规则: [...]   │
│                  │        │ 📋 notes.docx    │          │                  │
│                  │        │                  │          │ [开始提取]        │
└──────────────────┘        └──────────────────┘          └──────────────────┘
```

内部流程：文件 → MarkItDown 转 Markdown → LLM 一次性提取 entities/relations/logic/actions → 写入 Neo4j + ChromaDB。

> 这就是 v1 的 `run_extraction` Celery task，代码基本不变，只是输出目标从 PostgreSQL 改为同时写入 Neo4j 和 ChromaDB。

#### 2.4.3 本体详情页 — Tab 结构

两种路径构建完成后进入**相同的详情页**：

```
┌─────────────────────────────────────────────────────────────┐
│  📋 供应链知识图谱                               [导出 ▼]     │
│  ┌──────┬────────┬──────────┬───────┬────────┐              │
│  │ Info │ Graph  │ Entities │ Logic │Actions │              │
│  └──────┴────────┴──────────┴───────┴────────┘              │
│                                                              │
│  (Tab 内容区)                                                │
└─────────────────────────────────────────────────────────────┘
```

**各 Tab 说明**:

| Tab | 来源 | 变化 |
|-----|------|------|
| **Info** | 沿用 v1 `InfoTab.tsx` | 展示本体基本信息、构建方式、数据源、Mapping 状态；Pipeline Mapping 模式显示增量更新入口（见 2.4.4）；简易模式保留「选择模型+提示词+重新提取」按钮；导出按钮；质量报告 |
| **Graph** | 重构 v1 `GraphTab.tsx` | **Neo4j 原生渲染**（替换 Cytoscape.js，使用 Neovis.js）；**内置搜索栏**（支持关键词搜索 + 自然语言 → Cypher 查询 + 语义搜索定位实体）；邻居展开、路径查询、子图过滤、社区检测着色 |
| **Entities** | 沿用 v1 `EntitiesTab.tsx` | 保留实体列表 CRUD；**内置搜索栏**（关键词 + 语义搜索 + 类型筛选 + 置信度范围过滤）；分页加载 |
| **Logic** | v1 规则列表升级 | 展示 Validation / Mapping / Inference / State / Security / Automation 六类规则；支持启用/禁用、版本管理、关联实体筛选、规则测试和执行日志 |
| **Actions** | v1 动作列表升级 | 展示 Action Type 定义；支持参数表单、提交条件、执行效果、副作用、权限、版本管理、试运行和执行日志 |

**搜索能力说明**（分布在各 Tab 内，无独立 Search 页面）：

| 搜索模式 | 技术实现 | 出现在哪些 Tab |
|---------|---------|---------------|
| **关键词搜索** | Neo4j `CONTAINS` | Graph, Entities, Logic, Actions |
| **语义搜索** | ChromaDB 向量检索 | Graph（定位实体）, Entities（相似实体推荐） |
| **自然语言图查询** | LLM → Cypher → Neo4j | Graph（查询框） |
| **过滤器** | 类型/置信度/时间范围 | Entities, Logic, Actions |

**Graph Tab 详细设计**：

```
┌─────────────────────────────────────────────────────────────┐
│  Graph                                                        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 🔍 [搜索/查询: "华为的供应链上下游有哪些？"]           │    │
│  │ 模式: [自然语言 ▼] │ [Cypher 高级模式]                 │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  节点 142 │ 边 218 │ 布局 [力导向|层级|圆形]                  │
│  [🔍放大] [🔍缩小] [📐适应] [↻刷新]                          │
│  过滤: 类型 [全部▼]  置信度 [≥0.5]                            │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                                                        │    │
│  │              (Neo4j / Neovis.js 图谱渲染区)            │    │
│  │       右键节点: 展开1度/2度邻居 · 隐藏 · 查看详情      │    │
│  │       右键边: 查看关系详情 · 删除                       │    │
│  │                                                        │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  Legend:  🔵Organization  🟢Product  🟡Material  🟣Facility  │
│                                                               │
│  选中: 华为技术有限公司 (Organization) 置信度98%               │
│  邻居: 3个直接关联 │ [展开1度] [展开2度] [路径查询]           │
└─────────────────────────────────────────────────────────────┘
```

#### 2.4.4 增量更新（Pipeline Mapping 模式）

当本体通过 Pipeline Mapping 创建后，其关联的 Curated Datasets 可能随 Pipeline 重新运行而更新（例如数据源有新数据同步）。系统支持**增量更新**，流程如下：

```
数据源有新数据
    │
    ▼  Connection 自动/手动同步
    │
    ▼  Raw Dataset 新增版本 (APPEND)
    │
    ▼  Pipeline 自动/手动触发 (增量模式: 仅处理新增/变更行)
    │
    ▼  Curated Dataset 新增版本
    │     状态: pending_review (待审核)
    │
    ▼  用户在 Pipelines > Curated Datasets 中审核增量数据
    │     [✅ Approve]
    │
    ▼  Ontology 自动触发增量 Mapping
    │     - Neo4j: MERGE (存在则更新, 不存在则创建)
    │     - ChromaDB: upsert 更新向量
    │     - 显示增量 Mapping 进度条
    │
    ▼  Ontology 更新完成
```

**产品交互设计**：

1. **Curated Datasets 页面** — 已关联 Ontology 的数据集会显示关联标签：

```
│  ✅ clean_orders   │ 11,240行 │ 已审批 │ → 供应链知识图谱  │
│  ⚠️  clean_orders   │ +380行   │ 待审核 │ 增量: v4 (新)     │
│      [审核增量数据] [Approve → 自动更新Ontology]             │
```

2. **本体 Info Tab** — Pipeline Mapping 模式显示增量状态：

```
┌─────────────────────────────────────────────────────────────┐
│  Info                                                         │
│  名称: 供应链知识图谱 │ 领域: 供应链 │ 构建方式: Pipeline     │
│                                                               │
│  关联数据源:                                                   │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ clean_orders    │ 最近同步: 1h前 │ ✅ 已同步           │    │
│  │ clean_customers │ 最近同步: 1h前 │ ✅ 已同步           │    │
│  │ clean_products  │ 最近同步: 1h前 │ ⚠️ 有增量待审核     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  增量更新:                                                     │
│  上次更新: 2026-06-05 14:30 │ 实体变更: +12 修改 -0           │
│  [查看变更详情] [手动触发全量重建]                              │
│                                                               │
│  [导出 ▼]                                                     │
└─────────────────────────────────────────────────────────────┘
```

3. **自动触发规则** — Curated Dataset 被 Approve 后，若该数据集已关联某个 Ontology，系统自动触发该 Ontology 的增量 Mapping（Celery 异步任务），无需用户手动操作。

### 2.5 Settings — 系统设置

**页面**: `/settings`

从 v1 的 Settings 简化而来，原有的 Models 和 Prompts 已独立/移至 Models 页面。

**保留功能**:
- 用户管理（JWT auth, admin/user 角色）— 沿用 v1
- 规则配置（置信度阈值、显示规则）— 沿用 v1
- 导出格式设置

### 2.6 用户旅程

#### 旅程 A — Pipeline Mapping 全链路（三种数据类型全覆盖）

**场景**: 某制造企业需要构建供应链知识图谱。数据来自三类源头：ERP 系统的订单宽表（结构化）、供应商 API 返回的 JSON 报文（半结构化）、扫描的维修报告 PDF（非结构化）。

```
═══ 第一阶段: 配置模型 ═══

数据工程师:
  1. 在 Models 中配置两个模型:
     - DeepSeek V4 Flash (Compatible, 用于宽表分析/结构化提取/Mapping)
     - Anthropic Claude Sonnet (用于 VLM 文档提取)
  2. 在 Models 中配置提示词模板:
     - "供应链本体提取" (路径C LLM结构化提取用)
     - "通用宽表分析" (路径A 宽表拆分分析用)

═══ 第二阶段: 数据接入 (Pipelines > Connections) ═══

  3. 创建 Connection: MySQL-ERP-订单库
     - 类型: Database (MySQL)
     - 同步模式: SNAPSHOT, 频率: 每日 08:00
     - → 手动触发首次同步

  4. 创建 Connection: 供应商API
     - 类型: REST API
     - URL: https://supplier-api.example.com/v1/bookings
     - 同步模式: APPEND (增量), 频率: 每小时
     - → 手动触发首次同步

  5. 创建 Connection: 手动上传
     - 拖拽上传 156 个 PDF 维修报告
     - 系统自动识别为非结构化文件

═══ 第三阶段: 查看数据 (Pipelines > Datasets) ═══

  6. 数据自动出现:
     - 📊 erp_orders_raw      │ 结构化   │ 12,580行 │ 200列宽表
     - 📋 supplier_bookings   │ 半结构化  │ 8,230条JSON
     - 📄 maintenance_reports │ Media Set │ 156个PDF文件

═══ 第四阶段: 创建 Transform 管道 (Pipelines > Transforms) ═══

  7. 路径A — 结构化数据管道 (erp_orders_raw):
     系统检测到 200 列宽表 → 自动建议走大文件/宽表处理路径
     ① Schema 推断 → 确认列类型
     ② 数据清洗: 去重 3 行, Null 填充 47 处
     ③ 宽表拆分 (LLM=DeepSeek, Prompt=通用宽表分析):
        DeepSeek 分析 200 列 schema → 建议拆分为 4 张表
        用户确认: clean_orders / clean_customers / clean_products / clean_shipments
     ④ 输出: 4 个 Curated Dataset

  8. 路径B — 半结构化数据管道 (supplier_bookings):
     ① JSON 格式解析: 检测到嵌套 3 层 (booking → passenger → flights[])
     ② Flatten: passenger 对象摊平, flights 数组 explode 为多行
     ③ Schema 确认 + 清洗: 日期格式标准化, 编码转换
     ④ 输出: clean_bookings / clean_passengers (2 个 Curated Dataset)

  9. 路径C — 非结构化数据管道 (maintenance_reports):
     ① 文档提取策略选择: Layout-aware OCR + VLM (模型=Claude Sonnet)
     ② Markdown 输出: 156 个 PDF → 156 条 Markdown (带 media_reference)
     ③ LLM 结构化提取 (模型=DeepSeek, 提示词=供应链本体提取):
        用户定义目标 schema: tail_number / maintenance_date / issue_desc / parts_replaced
     ④ 输出: clean_maintenance (1 个 Curated Dataset)

  10. 运行全部 3 条管道, 在 Transforms 页面查看进度

═══ 第五阶段: 人工复核 (Pipelines > Curated Datasets) ═══

  11. 查看 7 个 Curated Dataset 的质量报告
  12. 逐一审核: 确认/修正/标记问题行
  13. 全部点击 [Approve]

═══ 第六阶段: 本体构建 (Ontologies) ═══

业务分析师:
  14. 在 Ontologies 点击「新建本体」→ 选择「Pipeline Mapping」
  15. 填写: 名称=供应链知识图谱, 领域=供应链
  16. 选择数据源: 勾选全部 7 个已审批的 Curated Datasets
  17. 确认 Mapping + Logic/Actions (LLM 辅助):
      - 7 个 Entity Type (Order, Customer, Product, Shipment, Booking, Passenger, MaintenanceRecord)
      - Property Mapping: 每张表的列 → 属性
      - Relation 推断: order_id FK关系, customer_id FK关系, tail_number FK关系 等
      - Logic Discovery: 校验规则、状态规则、图推导规则、自动化规则
      - Action Discovery: 审批、修复、状态流转、关系维护、外部写回动作
  18. 点击「开始构建」→ 查看 Mapping / Logic / Actions 发布进度条
  19. 构建完成 → 进入详情页
  20. 在 Graph Tab 用自然语言搜索: "华为供应链上下游有哪些?"
  21. 在 Entities Tab 按 Organization 类型筛选, 编辑补充信息
  22. 导出 Ontology (JSON / RDF / Neo4j dump)

═══ 第七阶段: 增量更新 (后续日常运营) ═══

  23. MySQL 每日同步新订单 → erp_orders_raw 新增版本
  24. 供应商 API 每小时同步 → supplier_bookings 新增 APPEND
  25. Pipeline 自动重跑 (增量模式: 仅处理新数据)
  26. Curated Dataset 出现增量待审核 → 用户 Approve
  27. 系统自动触发 Ontology 增量 Mapping → Neo4j MERGE 更新图谱
```

#### 旅程 B — 简易 LLM 提取（快速模式）

```
用户:
  1. 在 Models 中配置 DeepSeek 模型
  2. 在 Ontologies 中点击「新建本体」→ 选择「简易 LLM 提取」
  3. 填写名称、领域，上传 3 个 PDF 合同文件
  4. 选择模型 + 提示词（可用内置模板），点击「开始提取」
  5. 查看进度（排队 → 加载文件 → LLM提取 → 验证 → 保存）
  6. 完成后在 Graph / Entities / Logic / Actions Tab 查看结果
  7. 手动编辑/补充实体和关系
  8. 导出
```

### 2.7 系统流程图（泳道图）

以下泳道图展示两种构建路径的完整流程，按角色/模块划分泳道。

#### 路径一：Pipeline Mapping 全链路

```
┌─────────┬──────────────────────────────────────────────────────────────────────────┐
│         │                              时间轴 →                                    │
├─────────┼────────────────┬───────────────┬───────────────┬────────────┬────────────┤
│         │   数据接入      │   数据存储     │   数据转换     │  人工复核   │ 本体构建   │
├─────────┼────────────────┼───────────────┼───────────────┼────────────┼────────────┤
│         │                │               │               │            │            │
│ 数据    │ ① 配置Connector│               │               │            │            │
│ 工程师  │   (DB/API/文件) │               │ ④ 创建        │ ⑥ 审核     │            │
│         │ ② 触发同步     │               │   Transform   │   Curated  │            │
│         │                │               │   管道        │   Dataset  │            │
│         │                │               │               │   质量报告  │            │
│         │                │               │ ⑤ 运行管道    │   标注问题行│            │
│         │                │               │   查看进度    │            │            │
│         │                │               │               │ ⑦ Approve  │            │
│         │                │               │               │   ─────────┼──→         │
├─────────┼────────────────┼───────────────┼───────────────┼────────────┼────────────┤
│         │                │               │               │            │            │
│ 业务    │                │               │               │            │ ⑧ 新建本体 │
│ 分析师  │                │               │               │            │   选Pipeline│
│         │                │               │               │            │   Mapping  │
│         │                │               │               │            │ ⑨ 选Curated│
│         │                │               │               │            │   Datasets │
│         │                │               │               │            │ ⑩ 确认     │
│         │                │               │               │            │   Mapping  │
│         │                │               │               │            │ ⑪ 查看进度 │
│         │                │               │               │            │ ⑫ 探索图谱 │
│         │                │               │               │            │   导出     │
├─────────┼────────────────┼───────────────┼───────────────┼────────────┼────────────┤
│         │                │               │               │            │            │
│ 系统    │ Connection     │ ③ 数据落地    │ 路径自动选择: │ 质量报告   │ Mapping    │
│ (自动)  │ 调度器         │   Raw Dataset │               │ 自动生成   │ 引擎:      │
│         │ (Cron/手动)    │   (结构化)    │ 结构化→路径A  │            │ LLM建议→   │
│         │                │   Media Set   │  检测宽表→拆分│ Approve后  │ Entity Type│
│         │                │   (非结构化)  │ 半结构化→路径B│ ⚡自动触发  │ Property   │
│         │                │               │  JSON flatten │ Ontology   │ Relation   │
│         │                │ 特征检测:     │ 非结构化→路径C│ 增量Mapping │ 写Neo4j    │
│         │                │ 大文件?宽表?  │  OCR/VLM→LLM │            │ 写ChromaDB │
│         │                │ 深层嵌套?     │               │            │            │
│         │                │ 批量文档?     │ 输出→Curated  │            │            │
│         │                │               │ Dataset(s)    │            │            │
├─────────┼────────────────┼───────────────┼───────────────┼────────────┼────────────┤
│         │                │               │               │            │            │
│ 存储层  │                │ PostgreSQL    │ DuckDB        │ PostgreSQL │ Neo4j      │
│         │                │ (元数据)      │ (大文件处理)  │ (writeback)│ (图谱)     │
│         │                │ MinIO         │ Celery+Redis  │            │ ChromaDB   │
│         │                │ (原始文件)    │ (任务队列)    │            │ (向量)     │
│         │                │               │               │            │            │
└─────────┴────────────────┴───────────────┴───────────────┴────────────┴────────────┘
```

**流程要点说明**：

| 编号 | 步骤 | 关键决策/自动逻辑 |
|------|------|------------------|
| ①②③ | 数据接入 | Connector 同步后，系统自动检测数据特征：文件大小、列数、嵌套深度、文件数量。检测结果写入 `datasets.metadata`，供 Transform 步骤参考 |
| ④⑤ | 数据转换 | 系统根据数据类型自动推荐 Transform 路径。**大文件**(>500MB) 强制走 DuckDB 引擎；**宽表**(>80列) 自动推荐拆分步骤；用户可手动调整 |
| ⑥⑦ | 人工复核 | Approve 是增量更新的触发点——已关联 Ontology 的 Curated Dataset 被 Approve 后，系统自动创建 Celery mapping task |
| ⑧⑩ | Mapping | LLM 辅助生成映射建议（Entity Type / Property / Relation），随后执行 Logic Discovery 与 Action Discovery；用户确认后发布。进度条展示 Mapping、规则发现、动作发现、写入和发布阶段 |
| ⑫ | 探索 | 各 Tab 内置搜索（关键词/语义/图查询），Graph Tab 支持自然语言查询和邻居展开 |

#### 路径二：简易 LLM 提取

```
┌─────────┬───────────────────────────────────────────────────────────────┐
│         │                          时间轴 →                             │
├─────────┼──────────────┬──────────────┬──────────────┬─────────────────┤
│         │  创建本体     │  上传文件     │  LLM 提取    │  查看结果       │
├─────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│         │              │              │              │                 │
│ 用户    │ ① 新建本体   │ ② 拖拽上传   │ ③ 选模型     │ ⑤ 查看图谱      │
│         │    选「简易   │    PDF/DOCX  │   选提示词   │   编辑实体      │
│         │    LLM提取」 │    XLSX/CSV  │   点击「开始  │   编辑关系      │
│         │    填写名称   │    TXT/MD    │   提取」     │   导出          │
│         │    选领域     │              │              │                 │
│         │              │              │              │                 │
├─────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│         │              │              │              │                 │
│ 系统    │              │ MarkItDown   │ ④ Celery任务:│ 写入 Neo4j      │
│ (自动)  │              │ 转Markdown   │ 排队→加载→   │ 写入 ChromaDB   │
│         │              │              │ LLM提取→     │                 │
│         │              │              │ 验证→保存    │                 │
│         │              │              │              │                 │
│         │              │              │ 进度条展示   │                 │
│         │              │              │ 质量报告     │                 │
│         │              │              │              │                 │
├─────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│         │              │              │              │                 │
│ 存储层  │ PostgreSQL   │ MinIO        │ Redis/Celery │ Neo4j (图谱)    │
│         │ (本体元数据)  │ (原始文件)   │ LLM API调用  │ ChromaDB (向量) │
│         │              │              │              │                 │
└─────────┴──────────────┴──────────────┴──────────────┴─────────────────┘
```

#### 增量更新泳道

```
┌─────────┬──────────────┬──────────────┬──────────────┬─────────────────┐
│         │  数据源变更   │  Pipeline    │  人工复核     │  Ontology更新   │
├─────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│         │              │              │              │                 │
│ 数据    │              │              │ ③ 审核增量   │                 │
│ 工程师  │              │              │    数据      │                 │
│         │              │              │    Approve   │                 │
│         │              │              │    ──────────┼──→              │
│         │              │              │              │                 │
├─────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│         │              │              │              │                 │
│ 系统    │ ① Connection │ ② Pipeline  │              │ ④ ⚡自动触发     │
│ (自动)  │   定时同步   │   增量运行   │              │   增量Mapping   │
│         │   (Cron)     │   (仅处理    │              │   Neo4j MERGE   │
│         │   APPEND新数据│   新增/变更  │              │   ChromaDB      │
│         │              │   行)        │              │   upsert        │
│         │              │              │              │                 │
│         │   Raw Dataset│   Curated    │              │ ⑤ Ontology      │
│         │   版本 N+1   │   Dataset    │              │   版本 N+1      │
│         │              │   待审核     │              │   变更摘要:     │
│         │              │              │              │   +N ~N -N      │
│         │              │              │              │                 │
└─────────┴──────────────┴──────────────┴──────────────┴─────────────────┘
```

**增量更新关键机制**：
- **触发条件**: Curated Dataset 的 `status` 从 `pending_review` → `approved` 时，系统检查 `ontology_mappings` 表是否有关联记录
- **若有关联**: 自动创建 `mapping_tasks.incremental_sync` Celery 任务，无需用户手动操作
- **幂等保证**: Neo4j 使用 `MERGE` 语句（存在则更新、不存在则创建），ChromaDB 使用 `upsert`，重复触发不会产生脏数据

---

## 三、技术架构设计

### 3.1 整体架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Frontend (React + Vite)                          │
│                                                                           │
│  ┌──────────┐ ┌──────────────────────────────────────┐ ┌──────────┐     │
│  │ Overview │ │         Pipelines                      │ │Ontologies│     │
│  │          │ │ ┌────────┬────────┬─────────┬───────┐ │ │Info│Graph│     │
│  │          │ │ │Connect │Dataset │Transform│Curated│ │ │Ent │Logic│     │
│  │          │ │ └────────┴────────┴─────────┴───────┘ │ │Actions   │     │
│  └──────────┘ └──────────────────────────────────────┘ └──────────┘     │
│  ┌──────────┐ ┌──────────┐                                               │
│  │  Models  │ │ Settings │                                               │
│  └──────────┘ └──────────┘                                               │
└──────────┬───────────┬───────────┬────────────┬──────────┬──────────────┘
           │           │           │            │          │
           ▼           ▼           ▼            ▼          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       API Gateway (FastAPI)                                │
│  /api/v2/connections  /api/v2/datasets  /api/v2/pipelines                 │
│  /api/v2/ontologies   /api/v2/graph     /api/v2/search                    │
│  /api/v2/models       /api/v2/curated   /api/v2/mapping                   │
└──────┬───────────┬───────────┬────────────┬──────────┬──────────────────┘
       │           │           │            │          │
       ▼           ▼           ▼            ▼          ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Connection  │ │   Dataset    │ │   Pipeline   │ │   Ontology   │
│   Service    │ │   Service    │ │   Service    │ │   Service    │
│              │ │              │ │  (Celery)    │ │              │
│  Connector   │ │  Raw Store   │ │  Transform   │ │  Mapping     │
│  Registry    │ │  Version Mgr │ │  Engine      │ │  Engine      │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          Storage Layer                                     │
│                                                                            │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────┐  ┌───────────┐        │
│  │  PostgreSQL   │  │  MinIO / Local │  │  Neo4j   │  │ ChromaDB  │        │
│  │  (metadata,   │  │  (raw files,  │  │  (graph  │  │ (vector   │        │
│  │   pipeline    │  │   media set,  │  │   store) │  │  search)  │        │
│  │   config,     │  │   large data) │  │          │  │           │        │
│  │   curated,    │  │               │  │          │  │           │        │
│  │   models)     │  │               │  │          │  │           │        │
│  └──────────────┘  └───────────────┘  └──────────┘  └───────────┘        │
│                                                                            │
│  ┌──────────────┐                                                          │
│  │    Redis      │  (Celery broker + 缓存 + pipeline 状态)                 │
│  └──────────────┘                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈对比

| 层次 | 现有 (v1) | 新增/替换 (v2) | 选型理由 |
|------|-----------|---------------|---------|
| 前端 | React 18 + Vite + Tailwind | 保留，新增页面组件 | 无需更换 |
| 图谱渲染 | Cytoscape.js | **Neovis.js** (Neo4j 官方可视化库) | 原生 Neo4j 支持，替换 Cytoscape.js |
| 后端框架 | FastAPI | 保留，新增 router 模块 | 无需更换 |
| 任务队列 | Celery + Redis | 保留，扩展任务类型 | 无需更换 |
| 元数据存储 | SQLite / PostgreSQL | **PostgreSQL** (强制) | 需要事务+并发+JSONB |
| 文件存储 | 本地 `uploads/` 目录 | **MinIO** (开发环境可用本地文件) | S3 兼容，支持大文件和版本化 |
| 图数据库 | 无 (关系表模拟) | **Neo4j Community** | 原生图遍历、Cypher 查询 |
| 向量数据库 | 无 | **ChromaDB** | 轻量、嵌入式、Python 原生 |
| 文档提取 | MarkItDown | MarkItDown + **PaddleOCR** + **LLM VLM** | 三级提取策略 |
| 大文件处理 | 无 (全量加载内存) | **Apache Arrow** / **DuckDB** (嵌入式分析) | 列式处理，零拷贝 |
| Connector | 无 | **SQLAlchemy** + **PyMongo** + **httpx** | 统一接口 |

### 3.3 数据模型设计

#### 3.3.1 PostgreSQL 新增表

```sql
-- ===== Connection 层 =====

CREATE TABLE connections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    type            VARCHAR(50) NOT NULL,  -- 'database' | 'api' | 'file_upload'
    subtype         VARCHAR(50),           -- 'mysql' | 'postgresql' | 'mongodb' | 'sap_rfc' | 'rest_api'
    config          JSONB NOT NULL,        -- 加密存储的连接参数
    sync_mode       VARCHAR(20) DEFAULT 'snapshot',  -- 'snapshot' | 'append'
    sync_schedule   VARCHAR(100),          -- cron 表达式, NULL=手动
    status          VARCHAR(20) DEFAULT 'inactive',  -- 'active' | 'inactive' | 'error'
    last_sync_at    TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ===== Dataset 层 =====

CREATE TABLE datasets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    type            VARCHAR(20) NOT NULL,  -- 'raw' | 'curated' | 'media_set'
    format          VARCHAR(20),           -- 'tabular' | 'json' | 'xml' | 'document' | 'image'
    schema_info     JSONB,                 -- 列名、类型、约束
    connection_id   UUID REFERENCES connections(id),
    row_count       BIGINT DEFAULT 0,
    file_count      INTEGER DEFAULT 0,
    storage_path    TEXT,                  -- MinIO bucket/path
    current_version INTEGER DEFAULT 1,
    status          VARCHAR(20) DEFAULT 'active',
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE dataset_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID REFERENCES datasets(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    transaction_type VARCHAR(20) NOT NULL,  -- 'snapshot' | 'append' | 'update' | 'delete'
    row_count       BIGINT,
    change_summary  JSONB,                 -- {added: N, updated: N, deleted: N}
    storage_path    TEXT,                   -- 版本化存储路径
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE media_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID REFERENCES datasets(id) ON DELETE CASCADE,
    filename        VARCHAR(500) NOT NULL,
    mime_type       VARCHAR(100),
    file_size       BIGINT,
    page_count      INTEGER,
    storage_path    TEXT NOT NULL,          -- MinIO 路径
    extraction_status VARCHAR(20) DEFAULT 'pending',
    extracted_text  TEXT,                   -- Markdown 输出
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ===== Pipeline 层 =====

CREATE TABLE pipelines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    input_dataset_id UUID REFERENCES datasets(id),
    output_dataset_ids UUID[],             -- 多输出
    transform_path  VARCHAR(20) NOT NULL,  -- 'structured' | 'semi_structured' | 'unstructured'
    steps           JSONB NOT NULL,        -- 有序步骤配置数组
    schedule        VARCHAR(100),          -- cron 表达式
    status          VARCHAR(20) DEFAULT 'draft',
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID REFERENCES pipelines(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL,  -- 'queued' | 'running' | 'completed' | 'failed'
    trigger_type    VARCHAR(20),           -- 'manual' | 'scheduled' | 'connection_sync'
    progress        JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error           TEXT,
    run_stats       JSONB                  -- {rows_in, rows_out, duration_s, ...}
);

-- ===== Curated 层 (审核) =====

CREATE TABLE curated_reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID REFERENCES datasets(id),
    status          VARCHAR(20) DEFAULT 'pending_review',  -- 'pending_review' | 'in_review' | 'approved' | 'rejected'
    reviewer_id     UUID REFERENCES users(id),
    review_notes    TEXT,
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE curated_row_edits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id       UUID REFERENCES curated_reviews(id) ON DELETE CASCADE,
    row_key         TEXT NOT NULL,          -- 主键值标识
    edit_type       VARCHAR(20) NOT NULL,   -- 'approve' | 'modify' | 'delete' | 'flag'
    original_data   JSONB,
    modified_data   JSONB,
    edit_reason     TEXT,
    edited_by       UUID REFERENCES users(id),
    edited_at       TIMESTAMPTZ DEFAULT now()
);

-- ===== Ontology Mapping 层 =====

CREATE TABLE ontology_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ontology_id     UUID REFERENCES ontology_projects(id) ON DELETE CASCADE,
    dataset_id      UUID REFERENCES datasets(id),
    entity_type_name VARCHAR(200) NOT NULL,
    property_mappings JSONB NOT NULL,      -- [{column: "xxx", property: "yyy", type: "string"}, ...]
    primary_key_column VARCHAR(100),
    status          VARCHAR(20) DEFAULT 'draft',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ontology_link_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ontology_id     UUID REFERENCES ontology_projects(id) ON DELETE CASCADE,
    source_mapping_id UUID REFERENCES ontology_mappings(id),
    target_mapping_id UUID REFERENCES ontology_mappings(id),
    link_type       VARCHAR(100) NOT NULL,
    source_fk_column VARCHAR(100) NOT NULL,
    target_pk_column VARCHAR(100) NOT NULL,
    cardinality     VARCHAR(20) DEFAULT 'many_to_one',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ===== Ontology Logic 层 =====

CREATE TABLE ontology_logic_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ontology_id     UUID REFERENCES ontology_projects(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    logic_type      VARCHAR(50) NOT NULL,   -- 'validation' | 'mapping' | 'inference' | 'state' | 'security' | 'automation'
    description     TEXT,
    target_entity_type VARCHAR(200),
    expression      JSONB NOT NULL,         -- DSL/AST: conditions, predicates, graph pattern, state transitions
    source_type     VARCHAR(50),            -- 'transform' | 'mapping' | 'schema' | 'quality_report' | 'llm' | 'user'
    source_ref      JSONB,                  -- pipeline_id, step_id, dataset_id, column, prompt_id 等
    severity        VARCHAR(20) DEFAULT 'info', -- 'info' | 'warning' | 'error' | 'blocking'
    enabled         BOOLEAN DEFAULT true,
    status          VARCHAR(20) DEFAULT 'draft', -- 'draft' | 'published' | 'deprecated'
    version         INTEGER DEFAULT 1,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ontology_state_machines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ontology_id     UUID REFERENCES ontology_projects(id) ON DELETE CASCADE,
    entity_type_name VARCHAR(200) NOT NULL,
    state_property  VARCHAR(100) NOT NULL,
    states          JSONB NOT NULL,          -- [{name, label, terminal}]
    transitions     JSONB NOT NULL,          -- [{from, to, action_name, criteria}]
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ===== Ontology Actions 层 =====

CREATE TABLE ontology_action_types (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ontology_id     UUID REFERENCES ontology_projects(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    target_entity_type VARCHAR(200),
    action_category VARCHAR(50) NOT NULL,   -- 'crud' | 'link' | 'state_transition' | 'review' | 'repair' | 'writeback' | 'automation'
    parameters      JSONB NOT NULL,         -- [{name, type, required, enum_values, default}]
    submission_criteria JSONB,              -- rule refs / inline predicates
    effects         JSONB NOT NULL,         -- set property / create node / create link / delete / call function
    side_effects    JSONB,                  -- webhook/API/Celery task/notification
    permission_rules JSONB,                 -- roles, ownership, object-level conditions
    backed_by_function VARCHAR(200),        -- optional Python/TypeScript function name
    enabled         BOOLEAN DEFAULT true,
    status          VARCHAR(20) DEFAULT 'draft', -- 'draft' | 'published' | 'deprecated'
    version         INTEGER DEFAULT 1,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ontology_action_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type_id  UUID REFERENCES ontology_action_types(id),
    ontology_id     UUID REFERENCES ontology_projects(id) ON DELETE CASCADE,
    target_object_id TEXT,                  -- Neo4j node id/source_row_key
    parameters      JSONB NOT NULL,
    status          VARCHAR(20) NOT NULL,   -- 'queued' | 'running' | 'completed' | 'failed' | 'rolled_back'
    before_snapshot JSONB,
    after_snapshot  JSONB,
    side_effect_results JSONB,
    error           TEXT,
    executed_by     UUID REFERENCES users(id),
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
```

#### 3.3.2 Neo4j 图模型

```cypher
-- Entity Type 作为 Node Label
-- 每个 Curated Dataset 行 → 一个 Neo4j Node

-- 示例: 供应链场景
CREATE (s:Supplier {
  id: "uuid",
  name_cn: "华为技术有限公司",
  name_en: "Huawei Technologies",
  properties: {region: "深圳", level: "S级"},
  confidence: 0.98,
  source_dataset: "clean_suppliers",
  source_row_key: "S-001",
  created_at: datetime(),
  version: 1
})

CREATE (p:Product {
  id: "uuid",
  name_cn: "A18芯片",
  ...
})

CREATE (s)-[:SUPPLIES {
  type: "供货",
  confidence: 0.97,
  source_dataset: "clean_supply_relations"
}]->(p)

-- 增量更新: 用 MERGE 代替 CREATE
MERGE (s:Supplier {source_row_key: "S-001"})
SET s.name_cn = "华为技术有限公司",
    s.version = s.version + 1,
    s.updated_at = datetime()
```

#### 3.3.3 ChromaDB 向量模型

```python
# 每个 Entity 生成一条向量记录
collection = chroma_client.get_or_create_collection(
    name=f"ontology_{ontology_id}",
    metadata={"hnsw:space": "cosine"}
)

collection.upsert(
    ids=[entity_id],
    documents=[f"{entity.name_cn} {entity.description} {json.dumps(entity.properties)}"],
    metadatas=[{
        "entity_type": entity.type,
        "name_cn": entity.name_cn,
        "name_en": entity.name_en,
        "confidence": entity.confidence,
        "neo4j_node_id": neo4j_internal_id,
    }]
)

# 语义搜索
results = collection.query(
    query_texts=["哪些供应商提供芯片?"],
    n_results=10,
    where={"entity_type": "Supplier"}  # 可选过滤
)
```

### 3.4 大文件与宽表处理架构

#### 3.4.1 问题定义与自动检测

企业场景常见：
- **大文件**: 单个 CSV/Excel 超过 1GB，几百万行，pandas 直接加载会 OOM
- **宽表**: 200+ 列的 ERP 导出报表，不拆分就无法映射为独立 Entity Type
- **大量PDF**: 数千个文档需要 OCR/VLM 提取，需要批量流水线处理

**这些场景在 Pipeline 的 Connection → Dataset 阶段就需要自动识别**，而不是等到 Transform 时才发现问题。系统在数据进入 Raw Dataset 后立即进行特征检测，将检测结果写入 `datasets.metadata`，供后续 Transform 步骤自动选择处理策略。

#### 3.4.2 自动检测与路由逻辑

```
Connection 同步完成 / 文件上传完成
    │
    ▼
Raw Dataset 落地
    │
    ▼  ══ 自动特征检测 (DatasetAnalyzer) ══
    │
    ├─ 结构化数据检测:
    │   ├── file_size > 500MB ?              → 标记 large_file = true
    │   ├── column_count > 80 ?              → 标记 wide_table = true
    │   ├── row_count > 1,000,000 ?          → 标记 large_file = true
    │   └── 检测结果写入 datasets.metadata
    │
    ├─ 半结构化数据检测:
    │   ├── JSON nesting_depth > 3 ?         → 标记 deep_nested = true
    │   ├── 数组字段含 > 100 元素 ?          → 标记 array_explode_needed = true
    │   └── 检测结果写入 datasets.metadata
    │
    └─ 非结构化数据检测:
        ├── file_count > 100 ?               → 标记 batch_extraction = true
        ├── 单文件 page_count > 50 ?         → 标记 chunked_processing = true
        └── 检测结果写入 datasets.metadata

    │
    ▼  ══ Transform 自动策略选择 ══
    │
    ├─ large_file = true:
    │   → 强制使用 DuckDB 引擎 (流式处理, 不加载进内存)
    │   → 所有操作在 Parquet 文件上原地执行
    │
    ├─ wide_table = true:
    │   → Transform UI 自动推荐「宽表拆分」步骤
    │   → 调用 LLM 分析 schema, 建议拆分方案
    │   → 用户确认后, DuckDB 执行拆分写出多个 Curated Dataset
    │
    ├─ batch_extraction = true:
    │   → Transform 使用并发提取 (thread_number 可配置)
    │   → 进度条显示 X/N 文件
    │
    └─ 常规数据:
        → 标准 pandas/DuckDB 处理路径
```

**Datasets Tab 展示检测结果**:

```
│ 📊 erp_orders_raw  │ 结构化 │ 12,580行 │ 200列          │
│    ⚠️ 宽表(200列) — Transform 建议: 启用宽表拆分步骤     │
│    📏 文件大小: 1.2GB — 将使用 DuckDB 流式处理           │
```

#### 3.4.3 DuckDB 嵌入式分析引擎

选择 **DuckDB** 作为大文件/宽表场景的核心处理引擎（替代 pandas 全量加载）：

| 特性 | DuckDB | pandas | Spark |
|------|--------|--------|-------|
| 部署复杂度 | 嵌入式, 零配置 | 嵌入式 | 需要集群 |
| 内存使用 | 列式, 流式, 可 out-of-core | 全量加载 | 分布式内存 |
| 大文件 (>1GB) | ✅ 原生支持 | ❌ OOM 风险 | ✅ 过度工程 |
| Parquet 支持 | ✅ 原生 | ✅ 需 pyarrow | ✅ 原生 |
| SQL 兼容 | ✅ | ❌ | ✅ |
| 适合场景 | 单机百万~亿级 | 单机百万以内 | 集群亿级以上 |

```python
import duckdb

class DatasetService:
    """Dataset 存储和处理服务 — 大文件和宽表走 DuckDB 路径"""

    def __init__(self):
        self.conn = duckdb.connect()

    # ── 大文件检测 ─────────────────────────────────────────

    def analyze_dataset(self, file_path: str) -> dict:
        """Connection 同步后自动调用: 检测文件特征, 返回 metadata"""
        import os
        file_size = os.path.getsize(file_path)
        
        # DuckDB 流式推断 schema (不加载全量数据)
        schema = self.conn.execute(f"""
            SELECT column_name, column_type
            FROM (DESCRIBE SELECT * FROM read_csv_auto('{file_path}', sample_size=10000))
        """).fetchall()
        
        row_count = self.conn.execute(f"""
            SELECT count(*) FROM read_csv_auto('{file_path}')
        """).fetchone()[0]
        
        return {
            "file_size_bytes": file_size,
            "row_count": row_count,
            "column_count": len(schema),
            "columns": [{"name": s[0], "type": s[1]} for s in schema],
            "large_file": file_size > 500_000_000 or row_count > 1_000_000,
            "wide_table": len(schema) > 80,
        }

    # ── 大文件流式导入 ────────────────────────────────────

    def ingest_large_file(self, file_path: str, dataset_id: str):
        """流式导入大 CSV/Excel, 转为 Parquet, 不加载进内存"""
        self.conn.execute(f"""
            COPY (SELECT * FROM read_csv_auto('{file_path}'))
            TO 'storage/{dataset_id}/data.parquet'
            (FORMAT PARQUET, ROW_GROUP_SIZE 100000)
        """)

    # ── 宽表拆分 ──────────────────────────────────────────

    def split_wide_table(self, dataset_id: str, split_config: dict):
        """宽表拆分: 根据 LLM 建议 + 用户确认的 split_config 执行拆分
        
        split_config 示例:
        {
            "clean_orders": ["order_id", "customer_id", "product_id", "order_date", "amount"],
            "clean_customers": ["customer_id", "name", "email", "region"],
            "clean_products": ["product_id", "sku", "name", "category", "unit_price"],
        }
        每个 key → 一个独立的 Curated Dataset (Parquet 文件)
        """
        for output_name, columns in split_config.items():
            col_list = ", ".join(f'"{c}"' for c in columns)
            self.conn.execute(f"""
                COPY (
                    SELECT DISTINCT {col_list}
                    FROM 'storage/{dataset_id}/data.parquet'
                )
                TO 'storage/curated/{output_name}/data.parquet'
                (FORMAT PARQUET)
            """)

    # ── 通用操作 ──────────────────────────────────────────

    def infer_schema(self, dataset_id: str) -> list[dict]:
        """推断 schema (大文件场景: 直接从 Parquet metadata 读取, 零开销)"""
        result = self.conn.execute(f"""
            SELECT column_name, column_type, approx_count_distinct, null_percentage
            FROM (SUMMARIZE SELECT * FROM 'storage/{dataset_id}/data.parquet')
        """).fetchall()
        return [{"name": r[0], "type": r[1], "distinct": r[2], "null_pct": r[3]} for r in result]

    def preview(self, dataset_id: str, limit: int = 100) -> list[dict]:
        """零拷贝预览 — 直接从 Parquet 读取前 N 行"""
        return self.conn.execute(f"""
            SELECT * FROM 'storage/{dataset_id}/data.parquet' LIMIT {limit}
        """).fetchdf().to_dict(orient='records')
```

#### 3.4.4 文件存储策略

```
storage/
├── raw/
│   ├── {dataset_id}/
│   │   ├── v1/
│   │   │   ├── data.parquet        # 结构化数据统一转 Parquet
│   │   │   └── _metadata.json      # schema + 统计信息
│   │   ├── v2/
│   │   │   ├── data.parquet
│   │   │   └── _metadata.json
│   │   └── original/
│   │       └── raw_upload.csv      # 保留原始文件
│   └── ...
├── media/
│   ├── {media_set_id}/
│   │   ├── files/
│   │   │   ├── report_001.pdf
│   │   │   ├── report_002.pdf
│   │   │   └── ...
│   │   └── extracted/
│   │       ├── report_001.md       # VLM/OCR 提取的 Markdown
│   │       └── ...
│   └── ...
├── curated/
│   ├── {dataset_id}/
│   │   ├── data.parquet
│   │   └── writeback/              # 人工修改的增量记录
│   │       └── edits_v1.parquet
│   └── ...
└── temp/                           # Pipeline 中间结果
```

### 3.5 增量更新设计

#### 3.5.1 全链路增量流

```
Connection Sync (增量)
    │  APPEND 模式: 只拉取 last_sync_at 之后的新数据
    │  SNAPSHOT 模式: 全量替换 (用于不支持增量的源)
    ▼
Raw Dataset (新版本)
    │  dataset_versions 表记录 {added: N, updated: N, deleted: N}
    ▼
Pipeline Transform (增量模式)
    │  只处理新增/变更的行 (通过 version diff)
    │  输出: 新的 Curated Dataset 版本 (状态: pending_review)
    ▼
Curated Dataset (增量审核)
    │  只展示新增/变更的行供人工复核
    │  用户点击 [Approve]
    ▼
⚡ 自动触发: Ontology Mapping (增量同步)
    │  检测该 Curated Dataset 是否已关联某个 Ontology
    │  若已关联 → 自动创建 Celery mapping task
    │  Neo4j: MERGE 语句 (存在则更新, 不存在则创建)
    │  ChromaDB: upsert
    │  对比前后版本，找出:
    │    - 新增实体 → CREATE node
    │    - 变更实体 → SET properties, version++
    │    - 删除实体 → 标记 deleted (软删除)
    │    - 新增关系 → CREATE relationship
    │    - 变更关系 → SET properties
    │    - 删除关系 → DELETE relationship
    ▼
Ontology (版本 N+1)
    │  Info Tab 展示增量变更摘要: +N实体, ~N修改, -N删除
```

#### 3.5.2 Connection 增量同步实现

```python
class DatabaseConnector:
    """关系型数据库 Connector — 支持 SNAPSHOT 和 APPEND"""
    
    def sync(self, connection: Connection, dataset: Dataset):
        engine = create_engine(connection.config["connection_string"])
        
        if connection.sync_mode == "snapshot":
            # 全量替换
            df = pd.read_sql(connection.config["query"], engine)
            new_version = self.dataset_service.write_snapshot(dataset.id, df)
            
        elif connection.sync_mode == "append":
            # 增量追加: 使用时间戳水位线
            watermark = connection.last_sync_at or "1970-01-01"
            query = f"""
                {connection.config["query"]}
                WHERE {connection.config["watermark_column"]} > '{watermark}'
            """
            df = pd.read_sql(query, engine)
            if not df.empty:
                new_version = self.dataset_service.write_append(dataset.id, df)
        
        connection.last_sync_at = datetime.now(timezone.utc)


class APIConnector:
    """REST API Connector — 支持分页和增量"""
    
    async def sync(self, connection: Connection, dataset: Dataset):
        async with httpx.AsyncClient() as client:
            params = connection.config.get("params", {})
            if connection.sync_mode == "append" and connection.last_sync_at:
                params["since"] = connection.last_sync_at.isoformat()
            
            all_records = []
            url = connection.config["url"]
            while url:
                resp = await client.get(url, params=params, headers=connection.config.get("headers", {}))
                data = resp.json()
                records = data if isinstance(data, list) else data.get("data", data.get("results", []))
                all_records.extend(records)
                url = data.get("next")  # 分页
                params = {}  # 后续页不带原始 params
            
            if all_records:
                df = pd.json_normalize(all_records)
                if connection.sync_mode == "snapshot":
                    self.dataset_service.write_snapshot(dataset.id, df)
                else:
                    self.dataset_service.write_append(dataset.id, df)
```

#### 3.5.3 Pipeline 增量处理

```python
class IncrementalTransformEngine:
    """Pipeline 增量 Transform 引擎"""
    
    def run_incremental(self, pipeline: Pipeline, run: PipelineRun):
        dataset = self.get_dataset(pipeline.input_dataset_id)
        
        # 获取上次成功 run 的输入版本
        last_run = self.get_last_successful_run(pipeline.id)
        if last_run:
            last_input_version = last_run.run_stats.get("input_version")
            current_version = dataset.current_version
            
            if last_input_version == current_version:
                run.status = "skipped"  # 无新数据
                return
            
            # 获取增量数据 (version diff)
            delta_df = self.dataset_service.get_version_diff(
                dataset.id, 
                from_version=last_input_version,
                to_version=current_version
            )
        else:
            # 首次运行，处理全量
            delta_df = self.dataset_service.read_full(dataset.id)
        
        # 依次执行 Pipeline steps
        result_df = delta_df
        for step in pipeline.steps:
            result_df = self.execute_step(step, result_df)
        
        # 写入输出 (APPEND 模式)
        for output_dataset_id in pipeline.output_dataset_ids:
            self.dataset_service.write_append(output_dataset_id, result_df)
        
        run.run_stats = {
            "input_version": dataset.current_version,
            "rows_processed": len(delta_df),
            "rows_output": len(result_df),
        }
```

### 3.6 Neo4j 集成设计

#### 3.6.1 连接管理

```python
# backend/app/services/neo4j_service.py
from neo4j import GraphDatabase

class Neo4jService:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def sync_ontology(self, ontology_id: str, entity_type: str, 
                      entities: list[dict], relations: list[dict]):
        """将 Curated Dataset 同步到 Neo4j"""
        with self.driver.session() as session:
            # 批量 MERGE 实体
            session.execute_write(
                self._merge_entities, entity_type, entities, ontology_id
            )
            # 批量 MERGE 关系
            session.execute_write(
                self._merge_relations, relations, ontology_id
            )
    
    @staticmethod
    def _merge_entities(tx, entity_type: str, entities: list[dict], ontology_id: str):
        query = f"""
        UNWIND $entities AS e
        MERGE (n:{entity_type} {{source_row_key: e.source_row_key, ontology_id: $ontology_id}})
        SET n += e.properties,
            n.name_cn = e.name_cn,
            n.name_en = e.name_en,
            n.confidence = e.confidence,
            n.updated_at = datetime(),
            n.version = COALESCE(n.version, 0) + 1
        """
        tx.run(query, entities=entities, ontology_id=ontology_id)
    
    @staticmethod
    def _merge_relations(tx, relations: list[dict], ontology_id: str):
        query = """
        UNWIND $relations AS r
        MATCH (s {source_row_key: r.source_key, ontology_id: $ontology_id})
        MATCH (t {source_row_key: r.target_key, ontology_id: $ontology_id})
        MERGE (s)-[rel:RELATES_TO {type: r.type}]->(t)
        SET rel.confidence = r.confidence,
            rel.ontology_id = $ontology_id,
            rel.updated_at = datetime()
        """
        tx.run(query, relations=relations, ontology_id=ontology_id)
    
    def query_subgraph(self, ontology_id: str, cypher: str) -> dict:
        """执行 Cypher 查询，返回图数据"""
        with self.driver.session() as session:
            result = session.run(cypher, ontology_id=ontology_id)
            nodes, edges = [], []
            for record in result:
                for value in record.values():
                    if hasattr(value, 'labels'):  # Node
                        nodes.append({
                            "id": value.element_id,
                            "labels": list(value.labels),
                            "properties": dict(value)
                        })
                    elif hasattr(value, 'type'):  # Relationship
                        edges.append({
                            "id": value.element_id,
                            "source": value.start_node.element_id,
                            "target": value.end_node.element_id,
                            "type": value.type,
                            "properties": dict(value)
                        })
            return {"nodes": nodes, "edges": edges}
    
    def natural_language_query(self, ontology_id: str, question: str, 
                                llm_service) -> dict:
        """自然语言 → Cypher → 图查询"""
        # 获取 ontology 的 schema 信息
        schema = self._get_graph_schema(ontology_id)
        
        # LLM 将自然语言转为 Cypher
        cypher = llm_service.text_to_cypher(question, schema)
        
        # 执行 Cypher 并返回结果
        return self.query_subgraph(ontology_id, cypher)
```

#### 3.6.2 ChromaDB 集成

```python
# backend/app/services/chroma_service.py
import chromadb

class ChromaService:
    def __init__(self, persist_dir: str = "./chroma_data"):
        self.client = chromadb.PersistentClient(path=persist_dir)
    
    def sync_entities(self, ontology_id: str, entities: list[dict]):
        """同步实体到向量库"""
        collection = self.client.get_or_create_collection(
            name=f"ontology_{ontology_id}",
            metadata={"hnsw:space": "cosine"}
        )
        
        ids = [e["id"] for e in entities]
        documents = [
            f"{e.get('name_cn', '')} {e.get('name_en', '')} "
            f"{e.get('description', '')} {e.get('type', '')} "
            f"{json.dumps(e.get('properties', {}), ensure_ascii=False)}"
            for e in entities
        ]
        metadatas = [
            {
                "entity_type": e.get("type", ""),
                "name_cn": e.get("name_cn", ""),
                "name_en": e.get("name_en", ""),
                "confidence": e.get("confidence", 0),
            }
            for e in entities
        ]
        
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    
    def semantic_search(self, ontology_id: str, query: str, 
                        n_results: int = 10, filters: dict = None) -> list:
        """语义搜索实体"""
        collection = self.client.get_collection(f"ontology_{ontology_id}")
        
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
        }
        if filters:
            kwargs["where"] = filters
        
        results = collection.query(**kwargs)
        return results
```

### 3.7 Docker Compose (v2)

```yaml
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ontoprompt
      POSTGRES_USER: ontoprompt
      POSTGRES_PASSWORD: ontoprompt
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/ontoprompt123
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"   # Browser UI
      - "7687:7687"   # Bolt protocol
    volumes: [neo4j_data:/data]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Console UI
    volumes: [minio_data:/data]

  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [db, redis, neo4j, minio]
    volumes: [./backend:/app, ./storage:/storage]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  celery_worker:
    build: ./backend
    env_file: .env
    depends_on: [db, redis, neo4j, minio]
    volumes: [./backend:/app, ./storage:/storage]
    command: celery -A app.tasks.worker worker --loglevel=info --concurrency=4

  celery_beat:
    build: ./backend
    env_file: .env
    depends_on: [db, redis]
    volumes: [./backend:/app]
    command: celery -A app.tasks.worker beat --loglevel=info

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    volumes: [./frontend:/app, /app/node_modules]
    command: npm run dev -- --host

volumes:
  postgres_data:
  neo4j_data:
  minio_data:
```

### 3.8 API 设计 (v2)

#### 3.8.1 新增 API 端点

```
# ===== Pipelines 模块 =====

# Connection 管理 (/pipelines/connections)
POST   /api/v2/connections                 # 创建连接
GET    /api/v2/connections                 # 连接列表
GET    /api/v2/connections/{id}            # 连接详情
PUT    /api/v2/connections/{id}            # 更新连接配置
DELETE /api/v2/connections/{id}            # 删除连接
POST   /api/v2/connections/{id}/test       # 测试连接
POST   /api/v2/connections/{id}/sync       # 手动触发同步

# Dataset 管理 (/pipelines/datasets)
GET    /api/v2/datasets                    # 数据集列表
GET    /api/v2/datasets/{id}               # 数据集详情 + schema
GET    /api/v2/datasets/{id}/preview       # 数据预览 (分页)
GET    /api/v2/datasets/{id}/schema        # Schema 详情
PUT    /api/v2/datasets/{id}/schema        # 修改 schema (列重命名/类型修改)
GET    /api/v2/datasets/{id}/versions      # 版本历史
GET    /api/v2/datasets/{id}/stats         # 数据统计
POST   /api/v2/datasets/upload             # 文件上传入口 (统一替代原有)

# Transform 管道 (/pipelines/transforms)
POST   /api/v2/pipelines                   # 创建管道
GET    /api/v2/pipelines                   # 管道列表
GET    /api/v2/pipelines/{id}              # 管道详情
PUT    /api/v2/pipelines/{id}              # 更新管道配置
DELETE /api/v2/pipelines/{id}              # 删除管道
POST   /api/v2/pipelines/{id}/run          # 运行管道
GET    /api/v2/pipelines/{id}/runs         # 运行历史
GET    /api/v2/pipelines/{id}/runs/{run_id} # 运行详情+日志
POST   /api/v2/pipelines/suggest-split     # LLM 辅助宽表拆分建议
POST   /api/v2/pipelines/preview-step      # 预览某个 step 的输出

# Curated Dataset 管理与审核 (/pipelines/curated)
GET    /api/v2/curated                     # Curated Dataset 列表 (含审核状态)
GET    /api/v2/curated/{id}                # Curated Dataset 详情
GET    /api/v2/curated/{id}/data           # 数据预览 (分页, 含审核标记)
GET    /api/v2/curated/{id}/quality        # 质量报告
POST   /api/v2/curated/{id}/review         # 提交审核结果 (approve/reject)
PUT    /api/v2/curated/{id}/rows/{key}     # 修改单行 (writeback)
POST   /api/v2/curated/{id}/rollback       # 回退到上一版本

# ===== Models 模块 =====

# 模型管理 (沿用 v1 /api/v1/models 并扩展)
POST   /api/v2/models                      # 创建模型配置
GET    /api/v2/models                      # 模型列表
GET    /api/v2/models/{id}                 # 模型详情
PUT    /api/v2/models/{id}                 # 更新模型
DELETE /api/v2/models/{id}                 # 删除模型
POST   /api/v2/models/{id}/test            # 测试模型连接

# 提示词管理 (沿用 v1 /api/v1/prompts)
POST   /api/v2/prompts                     # 创建提示词
GET    /api/v2/prompts                     # 提示词列表
GET    /api/v2/prompts/{id}                # 提示词详情
PUT    /api/v2/prompts/{id}                # 更新提示词
DELETE /api/v2/prompts/{id}                # 删除提示词
POST   /api/v2/prompts/generate-template   # 自动生成提示词模板

# ===== Ontologies 模块 =====

# 本体 CRUD (沿用 v1 并扩展)
POST   /api/v2/ontologies                  # 创建本体 (body含 build_mode: "pipeline_mapping"|"simple_llm")
GET    /api/v2/ontologies                  # 本体列表
GET    /api/v2/ontologies/{id}             # 本体详情

# 简易 LLM 提取 (沿用 v1 extraction, 输出写入 Neo4j+ChromaDB)
POST   /api/v2/ontologies/{id}/files       # 上传文件 (简易模式)
POST   /api/v2/ontologies/{id}/extract     # 启动 LLM 提取 (model_id, prompt_id, constraints)
GET    /api/v2/ontologies/{id}/extract/{task_id}  # 提取进度查询

# Ontology Mapping (Pipeline模式)
POST   /api/v2/ontologies/{id}/mapping/suggest      # LLM 辅助映射建议
POST   /api/v2/ontologies/{id}/mapping/apply         # 应用映射 → 写入 Neo4j + ChromaDB
GET    /api/v2/ontologies/{id}/mapping               # 查看当前映射规则
PUT    /api/v2/ontologies/{id}/mapping               # 修改映射规则
POST   /api/v2/ontologies/{id}/mapping/resync        # 重新同步 (增量)

# 实体/逻辑/动作 (沿用 v1, 增加搜索参数)
GET    /api/v2/ontologies/{id}/entities    # 实体列表 (?q=关键词&type=&confidence_min=&page=&size=)
POST   /api/v2/ontologies/{id}/entities    # 创建实体
GET    /api/v2/ontologies/{id}/entities/{eid}  # 实体详情
PUT    /api/v2/ontologies/{id}/entities/{eid}  # 更新实体
DELETE /api/v2/ontologies/{id}/entities/{eid}  # 删除实体
GET    /api/v2/ontologies/{id}/logic       # 逻辑规则列表 (?q=关键词)
GET    /api/v2/ontologies/{id}/actions     # 动作列表 (?q=关键词)

# Graph (Neo4j 驱动)
GET    /api/v2/ontologies/{id}/graph                 # 获取图数据 (Neo4j Neovis.js 格式)
POST   /api/v2/ontologies/{id}/graph/cypher          # 执行 Cypher 查询
POST   /api/v2/ontologies/{id}/graph/nl-query        # 自然语言 → Cypher → 图数据
GET    /api/v2/ontologies/{id}/graph/neighbors/{node_id}  # N度邻居查询 (?depth=1)
GET    /api/v2/ontologies/{id}/graph/path             # 路径查询 (?from=&to=)
GET    /api/v2/ontologies/{id}/graph/communities      # 社区检测

# Search (各Tab内置搜索栏调用此API)
POST   /api/v2/ontologies/{id}/search                # 统一搜索后端
       # body: {query, mode: "keyword"|"semantic"|"graph", filters: {type, confidence_min}}
       # keyword → Neo4j CONTAINS
       # semantic → ChromaDB vector search
       # graph → LLM → Cypher → Neo4j
       # 由 Graph/Entities/Logic/Actions Tab 内的搜索栏调用

# 导出 (沿用 v1 并扩展)
GET    /api/v2/ontologies/{id}/export      # 导出 (?format=json|yaml|csv|turtle|html|neo4j_dump)

# ===== 保留 v1 兼容端点 (逐步废弃) =====
# /api/v1/* 保持不变，前端逐步迁移到 v2
```

### 3.9 后端模块新增

```
backend/
├── app/
│   ├── main.py                    # 扩展: 注册 v2 routers
│   ├── config.py                  # 扩展: Neo4j/MinIO/ChromaDB 配置
│   ├── database.py                # 保留
│   │
│   ├── models/                    # 扩展
│   │   ├── connection.py          # 🆕 Connection ORM
│   │   ├── dataset.py             # 🆕 Dataset + DatasetVersion ORM
│   │   ├── media_item.py          # 🆕 MediaItem ORM
│   │   ├── pipeline.py            # 🆕 Pipeline + PipelineRun ORM
│   │   ├── curated_review.py      # 🆕 CuratedReview + CuratedRowEdit ORM
│   │   ├── ontology_mapping.py    # 🆕 OntologyMapping + OntologyLinkMapping ORM
│   │   └── ...existing (entity, relation, ontology, prompt, model_config, etc.)...
│   │
│   ├── routers/
│   │   ├── v2/                    # 🆕 v2 API 路由 (按导航模块组织)
│   │   │   │
│   │   │   │  # Pipelines 模块 (4个子Tab对应4组路由)
│   │   │   ├── connections.py     # /api/v2/connections
│   │   │   ├── datasets.py        # /api/v2/datasets
│   │   │   ├── pipelines.py       # /api/v2/pipelines
│   │   │   ├── curated.py         # /api/v2/curated
│   │   │   │
│   │   │   │  # Models 模块
│   │   │   ├── models_v2.py       # /api/v2/models (扩展v1, 增加用途标签)
│   │   │   ├── prompts_v2.py      # /api/v2/prompts (沿用v1逻辑)
│   │   │   │
│   │   │   │  # Ontologies 模块
│   │   │   ├── ontologies_v2.py   # /api/v2/ontologies (双路径创建: pipeline_mapping / simple_llm)
│   │   │   ├── extraction_v2.py   # /api/v2/ontologies/{id}/extract (简易LLM提取, 沿用v1逻辑)
│   │   │   ├── mapping.py         # /api/v2/ontologies/{id}/mapping (Pipeline Mapping + 增量同步)
│   │   │   ├── graph_v2.py        # /api/v2/ontologies/{id}/graph (Neo4j + Neovis.js)
│   │   │   ├── entities_v2.py     # /api/v2/ontologies/{id}/entities (增加搜索过滤)
│   │   │   └── search.py          # /api/v2/ontologies/{id}/search (各Tab内置搜索的后端)
│   │   │
│   │   └── ...existing v1 routers (保持兼容)...
│   │
│   ├── services/
│   │   ├── neo4j_service.py       # 🆕 Neo4j 操作封装
│   │   ├── chroma_service.py      # 🆕 ChromaDB 操作封装
│   │   ├── minio_service.py       # 🆕 MinIO 文件存储封装
│   │   ├── dataset_service.py     # 🆕 Dataset CRUD + 版本管理 + DuckDB查询
│   │   ├── connector_service.py   # 🆕 Connector 注册 + 同步调度
│   │   ├── transform_service.py   # 🆕 Transform 引擎 (Pipeline 步骤编排)
│   │   ├── mapping_service.py     # 🆕 Ontology Mapping 引擎
│   │   ├── search_service.py      # 🆕 统一搜索服务 (关键词/语义/图)
│   │   └── ...existing (llm_service, document_service, encryption_service, etc.)...
│   │
│   ├── connectors/                # 🆕 Connector 实现
│   │   ├── base.py                # BaseConnector 抽象接口
│   │   ├── database_connector.py  # MySQL/PostgreSQL/MongoDB
│   │   ├── api_connector.py       # REST API
│   │   ├── file_connector.py      # 文件上传 (重构现有 document_service)
│   │   └── erp_connector.py       # SAP/用友/金蝶 (P1)
│   │
│   ├── transforms/                # 🆕 Transform Step 实现
│   │   ├── base.py                # BaseTransformStep 抽象接口
│   │   ├── schema_inference.py    # 自动推断 schema (DuckDB)
│   │   ├── data_clean.py          # 去重/null处理/格式化
│   │   ├── wide_table_split.py    # 宽表拆分 (LLM辅助 + 用户确认)
│   │   ├── json_flatten.py        # JSON/XML 摊平
│   │   ├── ocr_extract.py         # OCR 提取 (PaddleOCR)
│   │   ├── vlm_extract.py         # VLM 视觉提取 (调用 Models 中配置的VLM)
│   │   └── llm_structurize.py     # LLM 结构化提取 (调用 Models 中配置的LLM)
│   │
│   └── tasks/
│       ├── extraction.py          # 保留 (v1 兼容)
│       ├── sync_tasks.py          # 🆕 Connection 同步定时任务 (Celery Beat)
│       ├── pipeline_tasks.py      # 🆕 Pipeline 运行任务 (Celery Worker)
│       └── mapping_tasks.py       # 🆕 Ontology Mapping 写入任务
│
├── requirements.txt               # 新增依赖
└── Dockerfile
```

### 3.10 前端模块结构

```
frontend/src/
├── pages/
│   ├── overview/
│   │   └── OverviewPage.tsx              # 沿用 v1, 新增 pipeline/ontology 统计卡片
│   │
│   ├── pipelines/                        # 🆕 Pipelines 模块
│   │   ├── PipelinesLayout.tsx           # 🆕 Pipelines 页面 + 4个子Tab容器
│   │   ├── connections/
│   │   │   ├── ConnectionsTab.tsx        # 🆕 连接列表 + 新建连接
│   │   │   └── ConnectionForm.tsx        # 🆕 连接配置表单 (类型选择/认证/同步配置)
│   │   ├── datasets/
│   │   │   ├── DatasetsTab.tsx           # 🆕 数据集列表 (Raw + Media Set)
│   │   │   ├── DatasetPreview.tsx        # 🆕 数据预览 + Schema + 版本历史
│   │   │   └── MediaSetView.tsx          # 🆕 非结构化文件列表/预览
│   │   ├── transforms/
│   │   │   ├── TransformsTab.tsx         # 🆕 管道列表 + 运行状态
│   │   │   ├── PipelineEditor.tsx        # 🆕 管道编辑 (线性步骤卡片)
│   │   │   └── StepConfigPanel.tsx       # 🆕 步骤参数配置 (含模型选择器)
│   │   └── curated/
│   │       ├── CuratedTab.tsx            # 🆕 Curated Dataset 列表 + 审核状态
│   │       ├── CuratedReview.tsx         # 🆕 数据审核界面 (预览/标注/批准)
│   │       └── QualityReport.tsx         # 🆕 质量报告展示
│   │
│   ├── ontologies/                       # 重构 v1 ontologies
│   │   ├── list/
│   │   │   └── OntologyListPage.tsx      # 沿用 v1, 新增数据源信息展示
│   │   ├── new/
│   │   │   └── OntologyCreateWizard.tsx  # 🆕 新建本体向导 (双路径: Pipeline Mapping / 简易LLM提取)
│   │   └── detail/
│   │       ├── OntologyDetailPage.tsx    # 沿用 v1 Tab 结构 (Info/Graph/Entities/Logic/Actions, 各Tab内置搜索)
│   │       ├── tabs/
│   │       │   ├── InfoTab.tsx           # 沿用 v1 (Pipeline模式: 增量状态+Mapping入口; 简易模式: 保留提取按钮)
│   │       │   ├── GraphTab.tsx          # 重构: Neovis.js 渲染 + Neo4j 数据源 + 内置搜索/查询框 + 邻居展开
│   │       │   ├── EntitiesTab.tsx       # 沿用 v1 + 新增内置搜索栏/类型筛选/置信度过滤/分页
│   │       │   ├── LogicTab.tsx          # 沿用 v1 + 新增内置搜索过滤
│   │       │   ├── ActionsTab.tsx        # 沿用 v1 + 新增内置搜索过滤
│   │       │   └── FilesTab.tsx          # 沿用 v1 (仅简易LLM提取模式显示)
│   │       ├── entity/
│   │       │   └── EntityDetailPage.tsx  # 沿用 v1
│   │       ├── logic/
│   │       │   └── LogicDetailPage.tsx   # 沿用 v1
│   │       └── action/
│   │           └── ActionDetailPage.tsx  # 沿用 v1
│   │
│   ├── models/                           # 从 v1 models 扩展
│   │   └── ModelsPage.tsx                # 沿用 v1 + 新增提示词管理子区 + 用途标签
│   │
│   ├── settings/
│   │   └── SettingsPage.tsx              # 沿用 v1 (移除 Models/Prompts, 已独立)
│   │
│   └── login/
│       └── LoginPage.tsx                 # 沿用 v1
│
├── components/
│   ├── ConfidenceBar.tsx                 # 沿用 v1
│   ├── ConfirmDialog.tsx                 # 沿用 v1
│   ├── Layout.tsx                        # 更新: 新导航 (Overview|Pipelines|Ontologies|Models|Settings)
│   ├── StatusBadge.tsx                   # 沿用 v1
│   ├── SearchBar.tsx                     # 🆕 通用搜索组件
│   ├── ModelSelector.tsx                 # 🆕 模型选择器 (Pipeline步骤/Mapping中复用)
│   ├── DataTable.tsx                     # 🆕 通用数据表格 (分页/排序/筛选)
│   └── MiniGraph.tsx                     # 🆕 内嵌迷你图谱 (搜索结果子图展示)
│
├── api/
│   ├── client.ts                         # 沿用 v1
│   ├── auth.ts                           # 沿用 v1
│   ├── ontologies.ts                     # 沿用 v1 + 新增 v2 端点
│   ├── pipelines.ts                      # 🆕 Pipeline/Connection/Dataset/Curated API
│   ├── models.ts                         # 🆕 Models + Prompts v2 API
│   └── search.ts                         # 🆕 Search API
│
└── stores/
    ├── authStore.ts                      # 沿用 v1
    ├── uiStore.ts                        # 沿用 v1
    └── pipelineStore.ts                  # 🆕 Pipeline 运行状态管理
```

### 3.11 新增依赖

```txt
# requirements.txt 新增
neo4j==5.26.0                    # Neo4j Python driver
chromadb==0.5.23                 # ChromaDB 向量数据库
duckdb==1.2.0                    # 嵌入式分析引擎
minio==7.2.12                    # MinIO S3 client
pymongo==4.10.1                  # MongoDB connector
paddleocr==2.9.1                 # OCR 引擎 (可选, 容器内安装)
pyarrow==18.1.0                  # Arrow 列式处理
pandas>=2.2                      # 数据处理
python-crontab==3.2.0            # Cron 调度解析
```

```txt
# package.json 新增 (前端)
neovis.js                        # Neo4j 图谱可视化 (替换 cytoscape)
neo4j-driver                     # Neo4j JavaScript driver (Neovis.js 依赖)
```

---

## 四、实施路线图

### Phase 1 — 基础 Pipeline 框架 (4 周)

**目标**: 搭建全链路骨架，端到端可跑通

| 周 | 交付物 |
|----|--------|
| W1 | PostgreSQL 强制 + 新数据模型 migration；MinIO 文件存储替换本地 `uploads/`；Docker Compose v2 (含 Neo4j + MinIO) |
| W2 | Connection 模块: 文件上传 + MySQL/PostgreSQL connector；Dataset 层: Raw Dataset CRUD + 版本管理 + 数据预览 |
| W3 | Pipeline 框架: 路径A（结构化）的 schema inference + 清洗 + 预览；Celery pipeline task；**简易 LLM 提取路径迁移**（v1 extraction 改写为 Neo4j+ChromaDB 输出） |
| W4 | 前端新导航 + Connections 页面 + Datasets 页面 + Pipelines 页面骨架 |

### Phase 2 — Transform 三路径 + Neo4j (4 周)

| 周 | 交付物 |
|----|--------|
| W5 | 路径B: JSON flatten + XML 解析；路径C: MarkItDown + PaddleOCR + VLM 提取策略 |
| W6 | 宽表拆分功能 (LLM 辅助建议 + 用户确认 + 自动执行)；DuckDB 大文件处理 |
| W7 | Neo4j 集成: 写入 + Cypher 查询 + 图谱展示 (Neovis.js) |
| W8 | ChromaDB 集成: 向量化写入 + 语义搜索 API + 前端搜索框 |

### Phase 3 — 人工复核 + 增量更新 (3 周)

| 周 | 交付物 |
|----|--------|
| W9 | Curated Dataset 展示 + 质量报告 + 人工标注界面 |
| W10 | Ontology Mapping 自动化: LLM 辅助映射建议 + 用户确认 + Mapping 进度条 + 批量写入 Neo4j |
| W11 | 增量更新全链路: Connection append → Pipeline delta → Curated Approve → **自动触发 Ontology Mapping** → Neo4j MERGE |

### Phase 4 — 扩展 Connector + 打磨 (3 周)

| 周 | 交付物 |
|----|--------|
| W12 | MongoDB connector；REST API connector；Cron 自动调度 |
| W13 | 自然语言图谱查询；路径查询；邻居探索；社区检测可视化 |
| W14 | v1 → v2 迁移脚本；文档；性能测试 + 优化；ERP connector (SAP) 原型 |

---

## 五、关键设计决策记录

| # | 决策 | 选项 | 选择 | 理由 |
|---|------|------|------|------|
| 1 | 图数据库 | Neo4j vs ArangoDB vs Dgraph | **Neo4j Community** | 最成熟的生态、Cypher 查询语言最直观、前端可视化工具多、社区版免费可商用 |
| 2 | 向量数据库 | ChromaDB vs Milvus vs Weaviate | **ChromaDB** | 嵌入式部署最轻量、Python 原生、与项目规模匹配 |
| 3 | 大文件处理 | DuckDB vs Spark vs Polars | **DuckDB** | 单机嵌入式、零配置、SQL 兼容、足以覆盖百万行级数据 |
| 4 | 文件存储 | MinIO vs 本地文件 | **MinIO** (开发可降级为本地) | S3 兼容、版本化存储、生产环境可扩展 |
| 5 | OCR 引擎 | PaddleOCR vs Tesseract vs EasyOCR | **PaddleOCR** | 中文识别最佳、开源免费、活跃维护 |
| 6 | Pipeline 编排 | 自研 vs Airflow vs Prefect | **自研 (Celery task chain)** | 项目规模不需要重量级调度框架，Celery 已在 stack 中 |
| 7 | 前端图谱 | Neovis.js vs Cytoscape.js vs D3.js | **Neovis.js** | Neo4j 官方可视化库，原生 Cypher 驱动，与 Neo4j 后端深度集成；Cytoscape.js 不再保留 |
| 8 | API 版本策略 | v2 独立 vs v1 原地升级 | **v2 并行 + v1 兼容** | 平滑迁移，不破坏现有功能 |

---

## 六、风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| Neo4j Community 版不支持某些企业特性 (如集群) | 中 | 中 | 单机版足够当前规模；后续可迁移到 Neo4j Aura 或 NebulaGraph |
| DuckDB 处理超大数据集 (10GB+) 性能不足 | 低 | 高 | DuckDB 设计支持 out-of-core 处理；极端场景可引入 Spark |
| VLM 提取成本高 (每页调用一次 API) | 高 | 中 | 支持策略选择：优先传统 OCR，VLM 作为高级选项；批量处理复用缓存 |
| 增量更新的数据一致性 | 中 | 高 | 使用 PostgreSQL 事务保证元数据一致；Neo4j MERGE 操作天然幂等 |
| 宽表拆分的 LLM 建议质量不稳定 | 高 | 中 | LLM 建议仅作参考，始终需要人工确认；提供手动配置兜底 |

---

*本文档基于对 nano-ontoprompt v1 代码库的完整分析和 Palantir Foundry 五阶段数据链路的研究编写。*
