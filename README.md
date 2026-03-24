# challenge

《伤寒论》知识图谱项目。当前采用 `Vue 3 + Django + Neo4j`，覆盖文本检索、图谱浏览、模型辅助抽取、候选复核与已采纳记录导出。

## 目录结构

- `backend/`: Django API，建议运行环境为 conda `challenge`
- `frontend/`: Vue 3 + Vite 页面
- `data/`: 文本、词典、标注语料与处理中间结果
- `docs/`: 实施路线与协作文档
- `models/`: 本地模型 checkpoint 目录

## 本地运行

### Backend

```powershell
conda activate challenge
cd backend
python manage.py migrate
python manage.py runserver
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

前端默认读取 `http://127.0.0.1:8000/api/v1`，可通过 `frontend/.env.example` 或本地 `frontend/.env` 覆盖 `VITE_API_BASE_URL`。

图谱查询默认走本地 CSV 快照；如需切换为 Neo4j 在线查询，可在后端环境变量中设置：

- `GRAPH_QUERY_SOURCE=neo4j`
- 可选：`GRAPH_QUERY_FALLBACK_TO_CSV=true`（Neo4j 不可用时自动回退）

## 当前系统能力

- 图谱浏览与实体检索
- Neo4j 数据导入与查询
- `NER` 在线预测
- `RE` 单对和批量辅助判断
- 会话图谱导出
- 候选记录提交、筛选、状态复核
- 已采纳候选记录导出

## 常用脚本

### 预标注

```powershell
conda activate challenge
cd backend
python scripts/build_preannotations.py
```

### 候选样本筛选

```powershell
conda activate challenge
cd backend
python scripts/select_review_candidates.py --top-k 30
```

### 图谱 CSV 导出

```powershell
conda activate challenge
cd backend
python scripts/export_graph_csv.py
```

### 已采纳候选记录导出

```powershell
conda activate challenge
cd backend
python scripts/export_accepted_candidates.py
```

默认输出：

- `data/processed/annotation/accepted_candidates.jsonl`
- `data/processed/annotation/accepted_candidates_report.json`

## GitHub 上传建议

项目上传到 GitHub 时，建议只上传：

- 源代码
- `requirements.txt`
- `package.json` / `package-lock.json`
- 必要迁移文件
- 文档与说明
- 小规模样例数据

不要上传：

- `backend/.env`
- `frontend/.env`
- `models/baseline/`
- `data/processed/`
- `frontend/node_modules/`
- `frontend/dist/`
- `experiments/`

详细协作流程见：

- `docs/github-collaboration.md`

## 模型文件说明

当前仓库默认**不直接提交模型权重**。

如果其他人只需要查看系统、运行图谱和复核流程，不下载模型也可以使用大部分功能；缺失模型时，`NER/RE` 在线预测会提示 checkpoint 不存在。

如果需要完整使用模型能力，请将模型文件下载后放到：

- `models/baseline/ner/guwenbert-ner-baseline/best`
- `models/baseline/relation/guwenbert-relation-baseline/best`

建议的模型分发方式：

- Hugging Face
- GitHub Release
- 网盘 / OSS / 学校服务器

## 两人协作建议

建议采用：

- `main`: 稳定版本
- `dev`: 日常集成
- `feature/*`: 功能分支

每个人从 `dev` 拉自己的功能分支开发，完成后通过 Pull Request 合并回 `dev`，不要直接向 `main` 提交。
