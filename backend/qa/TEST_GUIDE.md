# 问答功能测试指南

## ✅ 已完成的工作

1. 后端 QA 接口：`backend/qa/views.py` - AskQuestionView
2. 路由注册：`backend/backend_config/urls.py` - `/api/v1/qa/ask/`
3. 前端页面：`frontend/src/views/QAPageView.vue` （已启用）
4. 路由配置：`frontend/src/router/index.ts` - `/qa`
5. 导航链接：`frontend/src/App.vue` - 添加了"智能问答"
6. API Key 已配置到 `backend/.env`

## 🚀 启动步骤

### 方式一：两个终端（推荐）

**终端 1 - 启动后端：**
```bash
cd /home/rosy/.openclaw/workspace/挑战杯-伤寒论项目/backend
source ../venv/bin/activate
python manage.py runserver
```

**终端 2 - 启动前端：**
```bash
cd /home/rosy/.openclaw/workspace/挑战杯-伤寒论项目/frontend
npm run dev
```

### 方式二：后台运行后端

```bash
# 后端（后台）
cd /home/rosy/.openclaw/workspace/挑战杯-伤寒论项目/backend
source ../venv/bin/activate
nohup python manage.py runserver 127.0.0.1:8000 > /tmp/django.log 2>&1 &
```

然后检查是否运行：
```bash
curl http://127.0.0.1:8000/api/v1/graph/summary/ | python3 -c "import sys,json; print(json.load(sys.stdin)['entity_node_count'])"
```

## 🧪 测试问答

1. 打开浏览器：`http://localhost:5173/#/qa`
2. 点击示例问题或输入：`桂枝汤包含哪些中药？`
3. 点击"提问"按钮

预期结果：
- 显示答案（包含实体关系、原文证据）
- 置信度显示（如 "85%"）
- 显示识别到的实体和相关实体列表

## 🔍 如果提问失败

### 检查 1：后端是否运行
```bash
ps aux | grep manage.py | grep -v grep
# 应该有输出
```

### 检查 2：后端接口是否正常
```bash
curl http://127.0.0.1:8000/api/v1/graph/summary/
# 应该返回 JSON
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/qa/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "桂枝汤"}'
# 应该返回 JSON 答案
```

### 检查 3：前端 API 配置
文件 `frontend/.env` 应包含：
```
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```
修改后需重启前端

### 检查 4：CORS
Django 设置 `CORS_ALLOW_ALL_ORIGINS=True` 或
`CORS_ALLOWED_ORIGINS` 包含 `http://localhost:5173`

### 检查 5：浏览器控制台
F12 → Network 标签 → 查看 `/api/v1/qa/ask/` 请求
- 状态码 200？还是 500/404？
- 点击查看 Response 内容

## 📝 API 文档

**端点**：`POST /api/v1/qa/ask/`

**请求体**：
```json
{
  "question": "桂枝汤包含哪些中药？"
}
```

**响应**：
```json
{
  "answer": "关于"桂枝汤"（方剂）：...",
  "confidence": 0.85,
  "entities": [
    {"type": "FORMULA", "text": "桂枝汤", "start": 0, "end": 3}
  ],
  "related_entities": [...],
  "cypher": null
}
```

## 🎯 可能的问题

1. **GLM API Key 未设置或过期**
   - 检查 `backend/.env` 中的 `GLM_API_KEY`
   - 已设置为：`6992796eb61c4990b6a9b388ccdf4b51.S7h5M7ptOiNhogsL`

2. **NER 服务不可用**
   - QA 接口会自动降级为关键词匹配
   - 查看日志：`tail -f /tmp/django.log`

3. **图谱数据缺失**
   - 检查 `data/processed/graph/` 下是否有 CSV 文件
   - 运行：`ls data/processed/graph/`

4. **端口冲突**
   - 后端默认 8000，前端 5173
   - 修改端口：`python manage.py runserver 127.0.0.1:8001`

## 📞 需要帮助？

如果仍有问题，请提供：
1. 后端控制台错误信息
2. 浏览器 Network 标签的请求/响应截图
3. `curl` 测试的输出
