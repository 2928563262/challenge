# Annotation Guideline

`text/实体与关系.docx` 给出的 V1 结构是当前最合适的标注基线，后续工程实现以它为准。

## Entity Types (V1)

- `CLAUSE`: 条文记录本身，默认由整条 `jsonl` 记录承载。
- `SYMPTOM`: 症状与体征，例如发热、恶寒、头痛、汗出。
- `SYNDROME`: 证候或病机标签，例如太阳病、中风、伤寒、风温。
- `FORMULA`: 方剂名，例如桂枝汤、白虎加人参汤。
- `HERB`: 中药名，例如桂枝、芍药、甘草、生姜。
- `THERAPY`: 治法与干预动作，例如发汗、下、温针。
- `ADMINISTRATION`: 煎服法，例如温服一升、日三服、啜热稀粥、覆取微似汗。

## Relation Types (V1)

- `CLAUSE_MENTIONS_ENTITY`: 条文提及实体。
- `SYNDROME_HAS_SYMPTOM`: 证候具有症状。
- `SYNDROME_TO_FORMULA`: 证候对应方剂。
- `FORMULA_CONTAINS_HERB`: 方剂包含中药。
- `SYNDROME_TO_THERAPY`: 证候采用治法。
- `FORMULA_HAS_ADMINISTRATION`: 方剂具有煎服法。

## Record Format

预标注文件采用 `jsonl`，每行一条条文记录：

```json
{
  "id": "line-0013",
  "text": "太阳病,头痛发热,汗出恶风,桂枝汤主之。",
  "entities": [
    {"id": "e1", "type": "SYNDROME", "text": "太阳病", "start": 0, "end": 3, "source": "dictionary"},
    {"id": "e2", "type": "SYMPTOM", "text": "头痛", "start": 4, "end": 6, "source": "dictionary"},
    {"id": "e3", "type": "FORMULA", "text": "桂枝汤", "start": 13, "end": 16, "source": "dictionary"}
  ],
  "relations": [
    {"type": "SYNDROME_HAS_SYMPTOM", "head": "e1", "tail": "e2", "source": "rule"},
    {"type": "SYNDROME_TO_FORMULA", "head": "e1", "tail": "e3", "source": "rule"}
  ],
  "meta": {
    "line_number": 13,
    "preannotation_methods": ["dictionary", "rule"]
  }
}
```

## Current Engineering Choice

- `CLAUSE_MENTIONS_ENTITY` 当前不单独展开成成百上千条边，先由每条记录天然承载。
- V1 先做弱监督预标注，不把模型输出直接当金标准。
- 金标准建议先从 200 到 500 条开始，优先覆盖高频方剂、高频症状和典型煎服法。

## Transformer Usage

- `guwenbert` 更适合作为预标注辅助或后续 NER 编码器，不建议直接替代人工标注。
- 当前脚本保留了 `--transformer-model` 参数位，后续可扩展为相似度排序或模型辅助建议。