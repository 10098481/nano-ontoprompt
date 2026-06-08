"""Neo4j 그래프 데이터베이스 서비스"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover
    GraphDatabase = None  # type: ignore


class Neo4jService:
    """Neo4j 연결 및 CRUD 서비스"""

    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        from app.config import settings
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver = None
        self._available = False
        self._init_driver()

    def _init_driver(self):
        try:
            if GraphDatabase is None:
                raise RuntimeError("neo4j package not installed")
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            self._driver.verify_connectivity()
            self._available = True
            logger.info("Neo4j connected")
        except Exception as e:
            logger.warning(f"Neo4j unavailable: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def close(self):
        if self._driver:
            self._driver.close()

    # ── 쓰기 ────────────────────────────────────────────────────────

    def upsert_entity(self, label: str, props: dict, key_field: str = "id") -> str | None:
        """엔티티 MERGE — 존재하면 업데이트, 없으면 생성"""
        if not self._available:
            return None
        query = f"""
        MERGE (n:{label} {{{key_field}: $key}})
        SET n += $props,
            n.updated_at = datetime()
        RETURN elementId(n) AS eid
        """
        with self._driver.session() as session:
            result = session.run(query, key=props.get(key_field), props=props)
            record = result.single()
            return record["eid"] if record else None

    def upsert_relation(self, src_label: str, src_key: str, tgt_label: str, tgt_key: str,
                        rel_type: str, props: dict | None = None, key_field: str = "id") -> bool:
        """관계 MERGE"""
        if not self._available:
            return False
        query = f"""
        MATCH (s:{src_label} {{{key_field}: $src_key}})
        MATCH (t:{tgt_label} {{{key_field}: $tgt_key}})
        MERGE (s)-[r:{rel_type}]->(t)
        SET r += $props, r.updated_at = datetime()
        RETURN r
        """
        with self._driver.session() as session:
            result = session.run(query, src_key=src_key, tgt_key=tgt_key, props=props or {})
            return result.single() is not None

    def batch_upsert_entities(self, label: str, entities: list[dict], key_field: str = "id") -> int:
        """배치 MERGE — 1000건씩 처리"""
        if not self._available or not entities:
            return 0
        query = f"""
        UNWIND $batch AS e
        MERGE (n:{label} {{{key_field}: e.key}})
        SET n += e.props, n.updated_at = datetime()
        """
        count = 0
        chunk_size = 1000
        with self._driver.session() as session:
            for i in range(0, len(entities), chunk_size):
                chunk = entities[i:i + chunk_size]
                batch = [{"key": e.get(key_field), "props": e} for e in chunk]
                session.run(query, batch=batch)
                count += len(chunk)
        return count

    # ── 읽기 ────────────────────────────────────────────────────────

    def run_cypher(self, query: str, params: dict | None = None) -> list[dict]:
        """Cypher 쿼리 실행"""
        if not self._available:
            return []
        with self._driver.session() as session:
            result = session.run(query, **(params or {}))
            return [dict(record) for record in result]

    def get_graph_data(self, ontology_id: str, limit: int = 200,
                       label_filter: str | None = None) -> dict:
        """그래프 시각화용 노드/엣지 데이터 반환 (分两步查询避免 LIMIT 吞掉边)"""
        if not self._available:
            return {"nodes": [], "edges": []}

        label_clause = f":{label_filter}" if label_filter else ""

        with self._driver.session() as session:
            # Step 1: 获取节点
            node_query = f"""
            MATCH (n{label_clause})
            WHERE n.ontology_id = $ontology_id
            RETURN n
            LIMIT $limit
            """
            nodes_map = {}
            node_result = session.run(node_query, ontology_id=ontology_id, limit=limit)
            for record in node_result:
                nd = record.get("n")
                if nd:
                    nid = nd.element_id
                    nodes_map[nid] = {"id": nid, "labels": list(nd.labels), "properties": dict(nd)}

            # Step 2: 获取这些节点之间的边
            if nodes_map:
                edge_query = """
                MATCH (n)-[r]->(m)
                WHERE n.ontology_id = $ontology_id AND m.ontology_id = $ontology_id
                RETURN r, n, m
                LIMIT 1000
                """
                edges = []
                node_id_set = set(nodes_map.keys())
                edge_result = session.run(edge_query, ontology_id=ontology_id)
                for record in edge_result:
                    r = record.get("r")
                    n2 = record.get("n")
                    m2 = record.get("m")
                    if r and n2 and m2:
                        if n2.element_id in node_id_set or m2.element_id in node_id_set:
                            if n2.element_id not in nodes_map:
                                nodes_map[n2.element_id] = {"id": n2.element_id, "labels": list(n2.labels), "properties": dict(n2)}
                            if m2.element_id not in nodes_map:
                                nodes_map[m2.element_id] = {"id": m2.element_id, "labels": list(m2.labels), "properties": dict(m2)}
                            edges.append({
                                "id": r.element_id,
                                "source": r.start_node.element_id,
                                "target": r.end_node.element_id,
                                "type": r.type,
                                "properties": dict(r),
                            })
            else:
                edges = []

        return {"nodes": list(nodes_map.values()), "edges": edges}

    def delete_by_ontology(self, ontology_id: str) -> int:
        """ontology_id에 연결된 모든 노드/관계 삭제"""
        if not self._available:
            return 0
        query = """
        MATCH (n {ontology_id: $ontology_id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        with self._driver.session() as session:
            result = session.run(query, ontology_id=ontology_id)
            record = result.single()
            return record["deleted"] if record else 0


def get_neo4j_service() -> Neo4jService:
    """싱글턴 팩토리"""
    return Neo4jService()
