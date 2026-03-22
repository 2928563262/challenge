# GitHub 协作说明

## 1. 仓库准备

本项目建议采用：

- `main`：稳定版本
- `dev`：日常集成分支
- `feature/*`：个人功能分支

建议不要直接向 `main` 提交。

## 2. 首次上传

在项目根目录执行：

```powershell
cd D:\code\python\challenge
git init
git branch -M main
git add .
git commit -m "Initial project commit"
```

然后把远程仓库连上：

```powershell
git remote add origin https://github.com/<your-account>/<repo-name>.git
git push -u origin main
```

再创建 `dev` 分支：

```powershell
git checkout -b dev
git push -u origin dev
```

## 3. 两人协作流程

每次开发前：

```powershell
git checkout dev
git pull origin dev
git checkout -b feature/<your-feature-name>
```

开发完成后：

```powershell
git add .
git commit -m "feat: 描述本次改动"
git push -u origin feature/<your-feature-name>
```

然后在 GitHub 发起 Pull Request，目标分支选择 `dev`。

## 4. 建议的提交信息

- `feat: 新增候选记录复核页`
- `fix: 修复关系预测类型约束`
- `docs: 更新 GitHub 协作说明`
- `refactor: 重构 annotation 导出逻辑`

## 5. 模型文件处理

模型权重不要直接提交到 Git 仓库。

建议做法：

- GitHub 仓库只放代码、依赖和说明
- 模型权重放到：
  - Hugging Face
  - GitHub Release
  - 网盘 / OSS / 学校服务器

然后在 `README.md` 中说明下载地址和放置目录。

## 6. 当前建议忽略上传的内容

- `backend/.env`
- `frontend/.env`
- `models/baseline/`
- `data/processed/`
- `frontend/node_modules/`
- `frontend/dist/`
- `experiments/`
- `tools/neo4j-import-run/`

## 7. 如果别人不下载模型

系统仍然可以使用：

- 图谱浏览
- 候选复核
- 数据导出
- 规则与已有数据驱动的展示功能

但 `NER/RE` 在线预测功能会因为缺少 checkpoint 而不可用。
