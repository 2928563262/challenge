# 图谱结构说明 V1

## 节点
- Entity（SYNDROME/SYMPTOM/FORMULA/HERB/THERAPY/ADMINISTRATION）
- Clause（条文）

## 关系
- SYNDROME_HAS_SYMPTOM
- SYNDROME_TO_FORMULA
- SYNDROME_TO_THERAPY（人工）
- FORMULA_CONTAINS_HERB
- FORMULA_HAS_ADMINISTRATION
- CLAUSE_MENTIONS_ENTITY

## 约束
- `Entity.entity_id` 唯一
- `Clause.clause_id` 唯一
- 关系去重键：`start_id + relation_type + end_id`
