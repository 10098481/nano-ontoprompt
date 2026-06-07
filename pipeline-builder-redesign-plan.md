# Pipeline Builder UI Redesign Plan

## 1. 背景与目标

当前 `nano-ontoprompt` 的 Pipeline 模块已经具备 v2 后端基础能力，包括 Connections、Datasets、Pipelines、Pipeline Runs、Curated Dataset 输出、宽表拆分 API 和部分 Transform 执行能力。但现有前端界面仍以四个 Tab 和 JSON steps textarea 为主，和 PRD 中参考 Palantir Foundry 的 Pipeline Builder 体验存在差距。

本方案目标是将 Pipeline UI 从“资源列表 + JSON 配置”升级为“Pipeline 列表 + 可视化画布编排 + 节点配置面板 + 可运行 DAG/线性执行计划”的工作台。

核心目标：

- 让用户从左侧导航进入“数据管道”后，首先看到 Pipeline 列表。
- 支持按 Pipeline ID、名称、业务域、状态查询。
- 支持新建、编辑、删除 Pipeline。
- 新建后进入 Pipeline Builder 编辑页。
- 编辑页使用 Canvas 表达数据流，节点包括 Connector、Storage、Transform、Output。
- 右侧详情面板按节点类型展示配置、预览、运行结果和血缘信息。
- Pipeline 最终输出 Curated Dataset，作为 Ontology Mapping 的唯一数据入口。
- UI 能表达 PRD 中结构化、半结构化、非结构化和大宽表四类处理路径。

## 2. 设计原则

### 2.1 PRD 对齐

Pipeline Builder 必须严格对应 PRD 的五阶段链路：

```text
Data Connection -> Raw Dataset / Media Set -> Pipeline Transform -> Curated Dataset -> Ontology Mapping
```

在 UI 节点上对应为：

```text
Connector -> Storage -> Transform -> Output
```

其中：

- Connector 对应 Data Connection。
- Storage 对应 Raw Dataset / Media Set。
- Transform 对应路径 A/B/C 和宽表拆分。
- Output 对应 Curated Dataset。
- Ontology Mapping 不放在 Pipeline Builder 内，只通过 approved Curated Dataset 衔接。

### 2.2 画布只负责编排，执行依赖结构化 DSL

Canvas 是用户交互层，不应直接成为后端执行格式。后端保存的 Pipeline definition 应是可验证、可版本化、可编译的结构化 JSON。

前端负责：

- 拖拽节点
- 连线
- 配置节点
- 保存 definition
- 展示验证错误
- 触发 run / publish

后端负责：

- 校验 DAG 结构
- 校验节点连接规则
- 将图编译为执行计划
- 执行 Connector sync / dataset storage / transform / output
- 记录 run、version、lineage、logs 和 output dataset

### 2.3 第一版必须可运行

UI 可以展示更多未来能力，但第一版可点击、可配置、可运行的操作必须和后端能力一致。

当前后端已经支持的 Transform 操作：

```text
rename_columns
drop_nulls
fill_nulls
drop_duplicates
normalize_dates
parse_json
parse_xml
document_to_markdown
```

其他操作如 Join、Aggregate、Window、Pivot、OCR、Embedding、Summarization 可以在 UI 中作为 disabled/future 操作展示，但不能伪装成可执行能力。

## 3. 信息架构

### 3.1 新 Pipeline 路由结构

建议路由：

```text
/pipelines
/pipelines/new
/pipelines/:pipelineId
/pipelines/:pipelineId/runs
/pipelines/:pipelineId/lineage
```

也可以继续复用当前 `/pipelines`，但页面结构应从四 Tab 改成 Pipeline List 为默认入口。

### 3.2 资源管理入口

原有 Connections、Datasets、Curated Datasets 不建议删除。它们可以改为以下形式之一：

方案 A：作为 Pipeline Builder 内的资源抽屉。

```text
Pipeline List
Pipeline Builder
Resource Library
  - Connections
  - Raw Datasets
  - Media Sets
  - Curated Datasets
```

方案 B：保留在 `/pipelines/resources` 下。

```text
/pipelines/resources/connections
/pipelines/resources/datasets
/pipelines/resources/curated
```

推荐方案 A，因为用户在画布里拖拽节点时更自然地使用资源库。

## 4. Pipeline 列表页

### 4.1 页面结构

用户点击左侧导航“数据管道”后，首先进入 Pipeline 列表页。

页面区域：

```text
┌──────────────────────────────────────────────────────────────┐
│ Pipelines                                      [新建 Pipeline] │
├──────────────────────────────────────────────────────────────┤
│ Search: ID / Name        Domain    Status      [Reset]        │
├──────────────────────────────────────────────────────────────┤
│ ID       Name       Domain   Status    Version  Branch  Action │
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 查询条件

支持：

- Pipeline ID 模糊查询
- Pipeline 名称模糊查询
- 业务域过滤
- 状态过滤
- 更新时间范围过滤

### 4.3 列表字段

推荐字段：

| 字段 | 说明 |
| --- | --- |
| ID | 自动生成，列表中显示前 8 位，hover 显示完整 ID |
| Name | Pipeline 名称 |
| Domain | 业务域 |
| Status | draft / editing / running / failed / published |
| Version | 当前版本，例如 v1、v2 |
| Branch | 当前分支，例如 main |
| Last Run | 最近一次运行状态和时间 |
| Updated At | 最近更新时间 |
| Actions | 查看编辑、复制、删除 |

### 4.4 行操作

每一行支持：

- 查看编辑：进入 Pipeline Builder 页面。
- 删除：二次确认后删除。
- 复制：后续可选，生成一个新 draft。

删除确认文案：

```text
确认删除 Pipeline「xxx」？
删除后不会删除已经生成的 Curated Dataset，但该 Pipeline 的编辑配置和运行记录将不可恢复。
```

## 5. 新建 Pipeline 弹窗

### 5.1 字段

点击“新建 Pipeline”后弹窗：

```text
Pipeline Name *
Business Domain *
Description

[取消] [确定]
```

建议补充内部默认值：

```text
id: server generated uuid
status: draft
version: v1
branch: main
definition:
  nodes: []
  edges: []
```

### 5.2 重名校验

后端应在创建时校验同一业务域下 Pipeline 名称唯一。

建议规则：

```text
unique(user_id, domain, name)
```

如果暂时没有多租户，可以先用：

```text
unique(domain, name)
```

错误提示：

```text
已存在同名 Pipeline，请更换名称。
```

### 5.3 创建成功行为

创建成功后直接进入编辑页：

```text
/pipelines/:pipelineId
```

如果用户从列表点击“查看编辑”，也进入同一个编辑页。

## 6. Pipeline Builder 编辑页

### 6.1 总体布局

```text
┌────────────────────────────────────────────────────────────────────┐
│ Pipeline Name  Status  Version v1  Branch main      [Run] [Publish] │
├───────────────┬─────────────────────────────────────┬──────────────┤
│ Tool Palette  │ Canvas                              │ Inspector    │
│               │                                     │              │
│ Connector     │  Connector -> Storage -> Transform  │ Config       │
│ Storage       │                       -> Output     │ Preview      │
│ Transform     │                                     │ Lineage      │
│ Output        │                                     │ Runs         │
└───────────────┴─────────────────────────────────────┴──────────────┘
```

### 6.2 顶部栏

顶部栏展示：

- Pipeline 名称
- 状态
- 当前版本
- 当前 branch
- 保存状态
- Run 按钮
- Publish 按钮
- Lineage 入口

建议按钮行为：

| 按钮 | 行为 |
| --- | --- |
| Save | 保存当前 draft definition |
| Run | 运行当前 draft |
| Publish | 将当前 draft 发布为稳定版本 |
| Lineage | 打开数据血缘视图 |
| Version | 查看历史版本 |
| Branch | 切换或创建分支，后续阶段实现 |

注意：Branch 和 Lineage 不应混用。

- Branch 是编辑分支语义。
- Lineage 是数据溯源语义。

### 6.3 左侧工具栏

工具栏建议分四类：

```text
Connector
Storage
Transform
Output
```

不建议第一版使用“结构器”作为一级工具分类，因为它容易和 schema、ontology 混淆。若保留“结构器”，建议作为 Transform 内的 `Structurize` 子能力。

### 6.4 Canvas 交互

支持：

- 从左侧拖拽节点到画布。
- 节点在画布内自由移动。
- 节点之间连接。
- 点击节点后右侧显示配置面板。
- 点击边后右侧显示连接配置或血缘说明。
- 删除节点时自动删除相关边。
- 保存节点 position。

推荐前端库：

```text
@xyflow/react
```

即 React Flow 的新包名。

### 6.5 节点连接规则

第一版强制连接规则，避免无效 DAG：

| Source | Target | 是否允许 |
| --- | --- | --- |
| Connector | Storage | 允许 |
| Storage | Transform | 允许 |
| Transform | Transform | 允许 |
| Transform | Output | 允许 |
| Storage | Output | 允许，表示 no-op passthrough |
| Connector | Transform | 不允许 |
| Connector | Output | 不允许 |
| Output | 任意节点 | 不允许 |

多个 Connector 可以连接同一个 Storage。

一个 Storage 可以连接多个 Transform，用于产生多个不同清洗输出。

一个 Transform 可以连接多个 Output，用于输出多个 Curated Dataset，但第一版可以限制为一个 Output，降低实现复杂度。

## 7. 节点模型

### 7.1 Connector 节点

Connector 表示外部数据源。

支持类型：

```text
file
postgresql
mysql
rest_api
mongodb
```

第一版可运行类型建议：

```text
file
postgresql/mock
mysql/mock
```

右侧面板 Tab：

```text
Config
Test
Sync
Lineage
```

Config 字段：

| 字段 | 说明 |
| --- | --- |
| Connector Name | 连接器名称 |
| Source Type | file / postgresql / mysql / rest_api / mongodb |
| Sync Mode | snapshot / append |
| Credentials | 密码、token 等敏感字段必须脱敏 |
| Schedule | cron 配置，后续接入 Celery beat |
| Query / Endpoint | DB query 或 REST endpoint |

Test Tab：

- 测试连接。
- 展示 schema sample。
- 展示错误日志。

Sync Tab：

- 手动同步。
- 最近同步时间。
- 同步状态。
- 新增/变更行数。

### 7.2 Storage 节点

Storage 表示数据落地层。

它根据 Connector 输入自动生成：

```text
Raw Dataset
Media Set
```

右侧面板 Tab：

```text
Config
Detected Data
Versions
Lineage
```

Config 字段：

| 字段 | 说明 |
| --- | --- |
| Storage Name | 存储节点名称 |
| Storage Mode | auto / raw_dataset / media_set |
| Versioning | snapshot / append |
| Retention | 保留策略 |
| Schema Inference | 是否自动推断 schema |

Detected Data 表格字段：

| 字段 | 说明 |
| --- | --- |
| Source Data Name | 源数据名称 |
| Source Data Type | CSV / XLSX / JSON / XML / PDF / DOCX / PNG 等 |
| Detected Data Type | structured / wide_structured / semi_structured / unstructured |
| Storage Type | raw_dataset / media_set |
| Rows / Files | 行数或文件数 |
| Columns | 列数 |
| Size | 数据大小 |
| Current Version | 当前版本 |

运行前该列表为空。

运行或同步成功后展示识别结果。

自动识别规则：

| 输入 | Detected Data Type | Storage Type |
| --- | --- | --- |
| CSV / XLSX / DB Table / Parquet | structured | raw_dataset |
| CSV / XLSX / DB Table 且列数 > 80 | wide_structured | raw_dataset |
| JSON / XML | semi_structured | raw_dataset |
| PDF / DOCX / PPTX / PNG / JPG | unstructured | media_set |
| 文件 > 500MB | large_file 标记 | raw_dataset 或 media_set |

### 7.3 Transform 节点

Transform 是 Pipeline Builder 的核心节点。

Transform Path：

```text
Path A: Structured
Path B: Semi-structured
Path C: Unstructured
Wide Table Split
```

默认策略：

| Storage 检测结果 | 推荐 Transform Path |
| --- | --- |
| structured | Path A |
| wide_structured | Path A + Wide Table Split |
| semi_structured | Path B |
| unstructured | Path C |

右侧面板 Tab：

```text
Config
Steps
Model
Preview
Validation
```

Config 字段：

| 字段 | 说明 |
| --- | --- |
| Transform Name | 节点名称 |
| Transform Path | auto / structured / semi_structured / unstructured / wide_table |
| Engine | pandas / duckdb / llm / ocr / embedding |
| Incremental Mode | off / append_only / delta |
| Error Policy | fail_fast / skip_bad_rows / quarantine |

### 7.4 Output 节点

Output 表示输出 Curated Dataset。

右侧面板 Tab：

```text
Config
Schema
Preview
Quality
Runs
Lineage
```

Config 字段：

| 字段 | 说明 |
| --- | --- |
| Output Name | Curated Dataset 名称 |
| Output Type | curated_dataset |
| Primary Key | 主键字段 |
| Review Required | 是否需要人工审核 |
| Status After Run | pending_review |

Output 规则：

- 无论路径 A/B/C，最终必须输出结构化 Curated Dataset。
- Output 默认状态为 `pending_review`。
- 只有 `approved` Curated Dataset 可以进入 Ontology Mapping。

## 8. Transform 操作目录

### 8.1 Path A: 结构化数据

适用：

```text
CSV
XLSX
Database Table
Parquet
```

操作目录：

| 操作 | 参数 | 当前后端状态 |
| --- | --- | --- |
| Rename Columns | mapping: old -> new | 已支持 |
| Drop Nulls | columns, threshold | 已支持部分 |
| Fill Nulls | values: column -> value | 已支持 |
| Drop Duplicates | subset columns | 已支持 |
| Normalize Dates | columns, timezone, output_format | 已支持部分 |
| Select Columns | columns | 待实现 |
| Filter | condition, columns | 待实现 |
| Sort | columns, direction | 待实现 |
| Join | left_dataset, right_dataset, keys, join_type | 待实现 |
| Aggregate | group_by, metrics, functions | 待实现 |
| Group By | group_by, aggregations | 待实现 |
| Window | partition_by, order_by, functions | 待实现 |
| Pivot | index, columns, values, agg_func | 待实现 |
| Union | datasets, mode | 待实现 |

建议第一版可编辑表单：

```json
{
  "op": "drop_duplicates",
  "columns": ["order_id"]
}
```

```json
{
  "op": "fill_nulls",
  "values": {
    "country": "UNKNOWN"
  }
}
```

### 8.2 Wide Table Split: 大宽表

触发条件：

```text
column_count > 80
```

或用户手动启用。

操作目录：

| 操作 | 参数 |
| --- | --- |
| Detect Wide Table | column_threshold, sample_rows |
| Suggest Split | max_groups, key_columns, model_id |
| Preview Split | selected_groups, limit |
| Apply Split | split_config, output_dataset_names |
| Validate Split | key_uniqueness, row_count_consistency |

右侧 UI 建议：

```text
Wide Table Split
- Column Count: 200
- Suggested Groups:
  - orders
  - products
  - suppliers
  - logistics
- Key Columns:
  - order_id
  - supplier_id
[Preview Split] [Apply Split]
```

### 8.3 Path B: 半结构化数据

适用：

```text
JSON
XML
Nested API Response
```

操作目录：

| 操作 | 参数 | 当前后端状态 |
| --- | --- | --- |
| Parse JSON | column, record_path, meta | 已支持 |
| Parse XML | column, row_path, fields | 已支持 |
| Flatten | max_depth, separator | 待实现 |
| Extract Field | path, output_column | 待实现 |
| Explode Array | array_path, keep_parent_fields | 待实现 |
| Normalize | target_schema | 待实现 |
| Schema Inference | sample_size, confidence_threshold | 待实现 |
| Join / Filter / Aggregate | 复用 Path A | 待实现 |

示例：

```json
{
  "op": "parse_json",
  "column": "raw_json",
  "record_path": ["orders"],
  "meta": ["supplier_id", "source_system"]
}
```

```json
{
  "op": "parse_xml",
  "column": "raw_xml",
  "row_path": "order",
  "fields": {
    "order_id": "@id",
    "supplier": "supplier",
    "amount": "amount"
  }
}
```

### 8.4 Path C: 非结构化数据

适用：

```text
PDF
DOCX
PPTX
PNG
JPG
TXT
Markdown
```

操作目录：

| 操作 | 参数 | 当前后端状态 |
| --- | --- | --- |
| Document to Markdown | path_column, output_column, keep_columns | 已支持 |
| OCR | language, dpi, page_range, engine | 待实现 |
| Chunking | chunk_size, overlap, split_strategy | 待实现 |
| Metadata Extraction | fields, mode | 待实现 |
| Entity Extraction | schema, model_id, prompt_id | 待实现 |
| Classification | labels, model_id, threshold | 待实现 |
| Embedding | embedding_model_id, dimension | 待实现 |
| Summarization | model_id, prompt, max_tokens | 待实现 |
| Structurize | output_schema, validation_rules | 待实现 |

示例：

```json
{
  "op": "document_to_markdown",
  "path_column": "storage_path",
  "output_column": "markdown",
  "keep_columns": ["media_reference", "mime_type"]
}
```

后续 Path C 的目标输出仍是结构化 Curated Dataset，例如：

```text
maintenance_report_id
equipment_id
fault_type
reported_at
action_taken
media_reference
```

## 9. Pipeline Definition DSL

### 9.1 当前格式问题

当前前端使用：

```json
{
  "steps": [
    {
      "op": "drop_duplicates"
    }
  ]
}
```

这个格式适合线性 Pipeline，但不适合画布、多个 Connector、Storage、Output 和血缘追踪。

### 9.2 建议新格式

```json
{
  "schema_version": "2.0",
  "nodes": [
    {
      "id": "connector_1",
      "type": "connector",
      "label": "ERP Orders",
      "position": { "x": 80, "y": 120 },
      "config": {
        "source_type": "postgresql",
        "connection_id": "..."
      }
    },
    {
      "id": "storage_1",
      "type": "storage",
      "label": "Raw Orders",
      "position": { "x": 320, "y": 120 },
      "config": {
        "storage_mode": "auto",
        "versioning": "snapshot"
      }
    },
    {
      "id": "transform_1",
      "type": "transform",
      "label": "Clean Orders",
      "position": { "x": 560, "y": 120 },
      "config": {
        "path": "auto",
        "engine": "pandas",
        "steps": [
          {
            "op": "drop_duplicates",
            "columns": ["order_id"]
          },
          {
            "op": "normalize_dates",
            "columns": ["order_date"]
          }
        ]
      }
    },
    {
      "id": "output_1",
      "type": "output",
      "label": "clean_orders",
      "position": { "x": 820, "y": 120 },
      "config": {
        "dataset_type": "curated_dataset",
        "review_required": true,
        "primary_key": ["order_id"]
      }
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source": "connector_1",
      "target": "storage_1"
    },
    {
      "id": "edge_2",
      "source": "storage_1",
      "target": "transform_1"
    },
    {
      "id": "edge_3",
      "source": "transform_1",
      "target": "output_1"
    }
  ]
}
```

### 9.3 兼容策略

为避免一次性破坏现有后端：

第一阶段继续支持旧格式：

```json
{
  "steps": []
}
```

第二阶段支持新格式：

```json
{
  "nodes": [],
  "edges": []
}
```

后端运行时：

- 如果 definition 有 `nodes` 和 `edges`，使用 DAG 编译器。
- 如果只有 `steps`，走现有线性执行逻辑。

## 10. 后端 API 调整建议

### 10.1 Pipeline CRUD

当前已有：

```text
GET    /api/v2/pipelines
POST   /api/v2/pipelines
GET    /api/v2/pipelines/{id}
PUT    /api/v2/pipelines/{id}
DELETE /api/v2/pipelines/{id}
POST   /api/v2/pipelines/{id}/run
GET    /api/v2/pipelines/{id}/runs
POST   /api/v2/pipelines/preview-step
POST   /api/v2/pipelines/suggest-split
POST   /api/v2/pipelines/preview-split
POST   /api/v2/pipelines/apply-split
```

建议补充：

```text
POST   /api/v2/pipelines/{id}/validate
POST   /api/v2/pipelines/{id}/publish
GET    /api/v2/pipelines/{id}/versions
GET    /api/v2/pipelines/{id}/lineage
POST   /api/v2/pipelines/{id}/compile
```

### 10.2 创建 Pipeline body

```json
{
  "name": "Supply Chain Cleaning",
  "domain": "供应链",
  "description": "ERP + supplier API cleaning pipeline"
}
```

### 10.3 保存 Pipeline definition

```json
{
  "name": "Supply Chain Cleaning",
  "domain": "供应链",
  "definition": {
    "schema_version": "2.0",
    "nodes": [],
    "edges": []
  }
}
```

### 10.4 Validate response

```json
{
  "valid": false,
  "errors": [
    {
      "node_id": "transform_1",
      "severity": "error",
      "message": "Transform node requires at least one input Storage node."
    }
  ],
  "warnings": [
    {
      "node_id": "storage_1",
      "severity": "warning",
      "message": "Detected wide table. Wide Table Split is recommended."
    }
  ]
}
```

## 11. 前端组件拆分建议

建议目录：

```text
frontend/src/pages/pipelines/
  PipelineListPage.tsx
  PipelineCreateModal.tsx
  PipelineBuilderPage.tsx
  builder/
    PipelineCanvas.tsx
    PipelineToolbar.tsx
    PipelineTopbar.tsx
    PipelineInspector.tsx
    nodes/
      ConnectorNode.tsx
      StorageNode.tsx
      TransformNode.tsx
      OutputNode.tsx
    inspectors/
      ConnectorInspector.tsx
      StorageInspector.tsx
      TransformInspector.tsx
      OutputInspector.tsx
    steps/
      StepCatalog.ts
      StepForm.tsx
      StructuredStepForm.tsx
      SemiStructuredStepForm.tsx
      UnstructuredStepForm.tsx
      WideTableStepForm.tsx
    validation/
      validateGraph.ts
      connectionRules.ts
```

API：

```text
frontend/src/api/pipelines.ts
```

需要扩展：

```ts
create(body)
update(id, body)
get(id)
validate(id)
publish(id)
lineage(id)
versions(id)
```

## 12. UI 状态设计

### 12.1 Pipeline 状态

```text
draft
editing
running
failed
published
archived
```

### 12.2 Node 状态

```text
empty
configured
invalid
running
success
failed
warning
```

### 12.3 Run 状态

```text
queued
running
success
failed
skipped
cancelled
```

### 12.4 Output 状态

```text
pending_review
approved
rejected
superseded
```

## 13. 运行与发布语义

### 13.1 Run

Run 是对当前 draft definition 的一次执行。

行为：

- 保存当前 definition。
- validate。
- compile execution plan。
- 执行。
- 记录 pipeline_run。
- 生成 raw dataset/media set 或 curated dataset 版本。
- 更新节点运行状态。

### 13.2 Publish

Publish 是将当前 draft 标记为稳定版本。

行为：

- 必须 validate 通过。
- 如果配置要求，可以要求最近一次 run 成功。
- 生成新 version。
- status 变为 published。

### 13.3 Branch

第一版只展示：

```text
main
```

后续再支持：

- 创建 branch
- 合并 branch
- 对比 branch definition

## 14. 数据血缘 Lineage

Lineage 不应和 Branch 混用。

Lineage 展示：

```text
Connector
  -> Raw Dataset / Media Set version
  -> Transform Run
  -> Curated Dataset version
  -> Ontology Mapping
```

建议第一版在 Pipeline Builder 右上角提供 Lineage 按钮，打开侧边抽屉或新页面。

Lineage 字段：

| 字段 | 说明 |
| --- | --- |
| Source | connector/source system |
| Dataset Version | raw dataset/media set version |
| Pipeline Run | run id/status/time |
| Output Version | curated dataset version |
| Downstream | linked ontology mapping |

## 15. 里程碑计划

### M1. Pipeline 列表页和创建流程

目标：

- Pipeline 默认入口改为列表页。
- 支持按 ID/name/domain/status 查询。
- 支持新建 Pipeline 弹窗。
- 支持重名校验。
- 创建后进入编辑页。

验收：

- 用户可以创建一个空 Pipeline。
- 重名时出现明确提示。
- 列表可以查看 draft/editing/published 状态。
- 删除需要二次确认。

### M2. Canvas MVP

目标：

- 引入 React Flow。
- 支持 Connector、Storage、Transform、Output 四类节点。
- 支持拖拽、移动、连线、删除。
- 保存和加载 nodes/edges。
- 实现基础连接规则。

验收：

- 用户可以画出 Connector -> Storage -> Transform -> Output。
- 刷新页面后节点位置和连线仍然存在。
- 非法连接被阻止或明确提示。

### M3. 右侧配置面板

目标：

- 不同节点展示不同配置面板。
- Connector 可选 source type 和配置。
- Storage 可显示自动识别结果。
- Transform 可配置当前后端已支持的 steps。
- Output 可配置 Curated Dataset 名称和 primary key。

验收：

- 不再要求用户手写 JSON steps。
- 当前已支持 transform ops 都有表单配置。
- Preview 可以调用后端 preview-step。

### M4. Run / Publish / Output

目标：

- Run 当前 Pipeline。
- 展示 run status、logs、errors。
- Output 生成 Curated Dataset。
- Publish 当前版本。

验收：

- 结构化 CSV 可以从 Storage -> Transform -> Output 跑通。
- Output 出现在 Curated Dataset 列表中，状态为 pending_review。
- Publish 后版本号更新。

### M5. Path B / Path C / Wide Table UI

目标：

- 半结构化 JSON/XML UI 表单化。
- 非结构化 document_to_markdown UI 表单化。
- 宽表 suggest/preview/apply 接入画布。

验收：

- JSON 可以 parse 成结构化 output。
- DOCX/PDF 可以生成 markdown 字段并输出 curated dataset。
- 宽表可以展示 split suggestion 并应用拆分。

### M6. 高级 Transform 能力扩展

目标：

- 后端补 Filter、Sort、Join、Aggregate、Group By、Pivot、Union。
- 前端 StepCatalog 同步开启对应操作。

验收：

- 多个 Storage 可以 join。
- Aggregate 输出 schema 可预览。
- 非法字段配置能被 validate 捕获。

## 16. 风险与取舍

### 16.1 不要只做视觉画布

风险：

画布看起来像 Foundry，但底层仍是 JSON textarea 或不可运行配置。

对策：

- 每个可点击操作必须对应后端可执行 op。
- 未实现能力使用 disabled 状态。
- Pipeline definition 必须可 validate。

### 16.2 第一版不要支持过多 DAG 形态

风险：

多个 Connector、多个 Transform、多个 Output 会导致执行计划复杂。

对策：

第一版支持：

```text
N Connector -> 1 Storage -> 1 Transform -> 1 Output
```

第二版再扩展：

```text
N Storage -> N Transform -> N Output
```

### 16.3 Branch 不要过早复杂化

风险：

Branch、version、publish、lineage 同时实现会拖慢进度。

对策：

第一版：

- branch 固定显示 main。
- version 支持自增。
- lineage 展示 run/output 链路。

后续再做 branch merge/diff。

## 17. 推荐优先级

最高优先级：

1. Pipeline 列表页。
2. 新建弹窗和重名校验。
3. Canvas 四节点。
4. 节点配置面板。
5. 当前已支持 transform ops 表单化。
6. Run 后输出 Curated Dataset。

中优先级：

1. 宽表 split UI。
2. JSON/XML Path B 表单。
3. document_to_markdown Path C 表单。
4. Lineage 抽屉。

后续优先级：

1. Join/Aggregate/Window/Pivot 等高级结构化操作。
2. OCR/VLM/Embedding/Summarization。
3. Branch 管理。
4. 多 Output DAG。

## 18. 最小可交付版本定义

最小可交付版本应满足：

- 用户进入 `/pipelines` 看到 Pipeline 列表。
- 用户可以新建 Pipeline。
- 用户进入 Builder 后可以拖拽四类节点。
- 用户可以连接 Connector -> Storage -> Transform -> Output。
- 用户可以配置 Transform 的已支持 steps。
- 用户可以运行 Pipeline。
- 运行成功后生成 Curated Dataset。
- Curated Dataset 可在后续 Ontology Mapping 中选择。

这个版本虽然还不是完整 Foundry，但已经完成了从当前 JSON 配置页面到 Pipeline Builder 的关键跃迁。
