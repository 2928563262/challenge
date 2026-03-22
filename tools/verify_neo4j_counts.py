from neo4j import GraphDatabase
import json

driver = GraphDatabase.driver("bolt://127.0.0.1:17687", auth=("neo4j", "neo4jpassword"))
queries = {
    "entity_count": "MATCH (e:Entity) RETURN count(e) AS value",
    "clause_count": "MATCH (c:Clause) RETURN count(c) AS value",
    "entity_relation_count": "MATCH ()-[r:SYNDROME_HAS_SYMPTOM|SYNDROME_TO_FORMULA|FORMULA_CONTAINS_HERB|FORMULA_HAS_ADMINISTRATION]->() RETURN count(r) AS value",
    "clause_mention_count": "MATCH ()-[r:CLAUSE_MENTIONS_ENTITY]->() RETURN count(r) AS value",
}
result = {}
with driver.session(database="neo4j") as session:
    for key, query in queries.items():
        result[key] = session.run(query).single()["value"]
driver.close()
print(json.dumps(result, ensure_ascii=False))
