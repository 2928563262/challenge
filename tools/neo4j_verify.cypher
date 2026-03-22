MATCH (e:Entity) RETURN count(e) AS entity_count;
MATCH (c:Clause) RETURN count(c) AS clause_count;
MATCH ()-[r:SYNDROME_HAS_SYMPTOM|SYNDROME_TO_FORMULA|FORMULA_CONTAINS_HERB|FORMULA_HAS_ADMINISTRATION]->() RETURN count(r) AS entity_relation_count;
MATCH ()-[r:CLAUSE_MENTIONS_ENTITY]->() RETURN count(r) AS clause_mention_count;
