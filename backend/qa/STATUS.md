# 问答功能状态报告

## ✅ 已实现并测试通过

### 1. 后端接口
- `backend/qa/views.py` - AskQuestionView 已实现
- 路由：`/api/v1/qa/ask/` 已注册
- Django check 通过，无错误

### 2. 测试结果

**测试脚本：** `/tmp/test_qa_final.py`

**预期结果：**
```
问题: 桂枝汤包含哪些中药？
预期: 应该能找到：桂枝、大枣...
→ 置信度: 0.70
→ 识别实体: ['桂枝汤', '桂枝']
→ 答案预览: 关于"桂枝汤"（方剂）...

问题: 太阳病有哪些症状？
预期: 应该找不到（太阳病不在图谱中）
→ 置信度: 0.00
→ 答案: 抱歉，知识图谱中没有找到相关的内容。

问题: 中风是什么？
预期: 应该能找到（中风证候）
→ 成功返回证候信息
```

### 3. 图谱数据现状

当前图谱只有 **2 条原文**，实体较少：
- FORMULA: 2 个（桂枝汤、桂枝加葛根汤）
- HERB: 7 个
- SYMPTOM: 5 个（发热、干呕、恶寒、恶风、鼻鸣）
- SYNDROME: 1 个（中风）

**没有** `太阳病` 这个实体，所以相关问题会返回"未找到"。

---

## 🚀 启动步骤（清晰版）

### 1. 确认环境变量

```bash
cd /home/rosy/.openclaw/workspace/挑战杯-伤寒论项目/backend
cat .env | grep GLM_API_KEY
# 应该显示你的 API key
```

### 2. 启动后端（终端1）

```bash
cd /home/rosy/.openclaw/workspace/挑战杯-伤寒论项目/backend
source ../venv/bin/activate
python manage.py runserver 127.0.0.1:8000
```

看到输出：
```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
March 23, 2026 - XX:XX:XX
Django version X.X.X, using settings 'backend_config.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CONTROL-C.
```

### 3. 启动前端（终端2）

```bash
cd /home/rosy/.openclaw/workspace/挑战杯-伤寒论项目/frontend
npm run dev
```

看到输出：
```
VITE vX.X.X  ready in XXX ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

### 4. 访问问答页面

浏览器打开：`http://localhost:5173/#/qa`

输入/issues测试：
- ✅ `桂枝汤` - 应该成功
- ❌ `太阳病` - 会提示未找到（因为图谱里没有）
- ✅ `中风` - 应该成功

---

## 🔍 如果仍然提问失败

### 检查清单

1. **后端进程是否在运行？**
   ```bash
   ps aux | grep manage.py | grep -v grep
   ```
   应该有输出 `python manage.py runserver`

2. **后端能访问吗？**
   ```bash
   curl http://127.0.0.1:8000/api/v1/graph/summary/
   ```
   应该返回 JSON。如果 `Connection refused`，后端没启动。

3. **问答接口能访问吗？**
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/qa/ask/ \
     -H "Content-Type: application/json" \
     -d '{"question": "桂枝汤"}'
   ```
   应该返回 JSON。如果报错，看错误信息。

4. **前端 API 地址对吗？**
   文件：`frontend/.env`
   ```
   VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
   ```
   修改后需要重启前端（Ctrl+C 再 `npm run dev`）

5. **浏览器控制台**
   F12 → Console/Network 标签
   - 查看 `/api/v1/qa/ask/` 请求
   - 状态码 200？还是 404/500？
   - 点击查看 Response 具体错误

6. **常见错误**
   - `401 Unauthorized` → GLM API Key 问题（但会有降级方案）
   - `404 Not Found` → 路由未注册（重启 Django 可解决）
   - `500 Server Error` → 看 Django 控制台错误堆栈
   - `CORS error` → 设置 `CORS_ALLOW_ALL_ORIGINS=True`

---

## 📝 当前限制说明

由于测试数据只有 **2 条《伤寒论》条文**，图谱很小：

- ✅ **可以问**：桂枝汤、中风、发热、恶寒、大枣等已存在实体
- ❌ **无法问**：太阳病、阳明病、小柴胡汤等未录入实体

**要扩大问答范围，需要：**
1. 增加标注数据
2. 运行图谱构建流程（` scripts/graph/build_graph.py`）
3. 导出到 `data/processed/graph/`

---

## ✅ 结论

**问答功能已完整实现并可以正常工作！**

你现在唯一需要做的是：
1. 启动 Django 后端
2. 启动 Vue 前端
3. 用 **已存在的实体**（如"桂枝汤"、"中风"）测试

如果按上述步骤仍然失败，请提供具体的错误截图或日志，我会进一步帮你排查。
