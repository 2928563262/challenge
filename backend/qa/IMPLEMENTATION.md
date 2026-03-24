# 智能问答功能实现总结

## 完成时间
2026-03-23

## 功能说明
为《伤寒论》知识图谱系统添加基于自然语言的智能问答功能。

## 实现内容

### 前端（乙负责）
1. **启用问答页面**
   - 将 `QAPageView.vue.disabled` 重命名为 `QAPageView.vue`
   - 调整样式以匹配项目整体风格（使用项目主色调 #7d4f2b）
   - 优化移动端体验

2. **路由配置**
   - `frontend/src/router/index.ts`：添加 `/qa` 路由
   - `frontend/src/App.vue`：导航栏添加"智能问答"链接

3. **API 适配**
   - `frontend/src/types/api.ts`：添加 `QAAnswer` 接口定义
   - `frontend/src/services/api.ts`：添加 `askQuestion` 函数

### 后端（乙独立实现）
1. **新建 qa Django app**
   - `backend/qa/views.py`：实现 `AskQuestionView`
   - `backend/qa/urls.py`：路由配置
   - `backend/qa/apps.py`：AppConfig
   - `backend/qa/__init__.py`：模块标记

2. **注册应用**
   - `backend/backend_config/settings.py`：添加 `'qa'` 到 `INSTALLED_APPS`
   - `backend/backend_config/urls.py`：添加 `path("api/v1/qa/", include("qa.urls"))`

## 技术设计

### 问答流程
1. **实体识别**：调用 `modeling.services.predict_ner` 识别问题中的实体
2. **图谱搜索**：调用 `graph.services.search_entities` 查找相关实体
3. **详情获取**：调用 `graph.services.get_entity_detail` 获取实体的关系和原文证据
4. **答案生成**：根据图谱信息组织成自然语言回答（模板填充）

### 置信度计算
基于：
- 实体被提及次数（mention_count）
- 入边/出边数量（关系丰富度）
- 识别到的实体数量

## 接口文档

**端点**：`POST /api/v1/qa/ask/`

**请求**
```json
{
  "question": "桂枝汤包含哪些中药？"
}
```

**响应**
```json
{
  "answer": "关于“桂枝汤”（方剂）：它在知识图谱中关联...",
  "confidence": 0.85,
  "entities": [
    {"type": "FORMULA", "text": "桂枝汤", "start": 0, "end": 3}
  ],
  "related_entities": [...],
  "cypher": null
}
```

## 测试建议

1. 启动 Django 后端：`cd backend && python3 manage.py runserver`
2. 启动 Vue 前端：`cd frontend && npm run dev`
3. 访问 `http://localhost:5173/#/qa`
4. 尝试示例问题：
   - "桂枝汤包含哪些中药？"
   - "太阳病有哪些症状？"
   - "大承气汤的组成？"

## 注意事项

- 问答功能依赖 NER 模型服务和知识图谱数据
- 如果 NER 未识别到实体，会返回提示信息
- 如果图谱中无相关实体，会返回"未找到"提示
- 当前使用模板生成答案，后续可扩展为 LLM 生成

## 协作说明

- 前端页面由乙独立完成
- 后端接口由乙独立实现，调用了甲维护的 `modeling` 和 `graph` 模块
- 如需修改实体类型或关系类型，需要与甲同步