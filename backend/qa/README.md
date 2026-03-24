# QA Backend App

智能问答后端模块。

## 结构

- `views.py` - AskQuestionView 实现
- `urls.py` - 路由配置 `/api/v1/qa/ask/`
- `apps.py` - Django app 配置

## 功能

AskQuestionView 实现基于知识图谱的问答：

1. 用 NER 识别问题中的实体
2. 在知识图谱中搜索相关实体
3. 获取实体详细信息（关系、原文证据）
4. 组织成自然语言答案

## 依赖

- `backend.modeling.services.predict_ner`
- `backend.graph.services.search_entities`, `get_entity_detail`

## 接口

**POST** `/api/v1/qa/ask/`

```json
{
  "question": "桂枝汤包含哪些中药？"
}
```

**响应**

```json
{
  "answer": "关于“桂枝汤”（方剂）：...",
  "confidence": 0.85,
  "entities": [...],
  "related_entities": [...],
  "cypher": null
}
```