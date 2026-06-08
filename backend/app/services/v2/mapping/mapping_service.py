"""Ontology Mapping 执行服务 — PRD v1.1: Entity Mapping + Relation推断 + ChromaDB写入"""
from __future__ import annotations
import logging
import uuid as _uuid
from sqlalchemy.orm import Session
from app.models.v2.mapping import OntologyMapping

logger = logging.getLogger(__name__)


class MappingService:

    def __init__(self, db: Session):
        self._db = db

    # ── CRUD ─────────────────────────────────────────────────────────

    def create_mapping(self, ontology_id: str, curated_dataset_id: str, entity_class: str,
                       field_mapping: dict, primary_key_column: str | None = None,
                       confidence: float = 1.0) -> OntologyMapping:
        mapping = OntologyMapping(
            ontology_id=ontology_id, curated_dataset_id=curated_dataset_id,
            entity_class=entity_class, field_mapping=field_mapping,
            status="draft", confidence=confidence,
        )
        self._db.add(mapping); self._db.commit(); self._db.refresh(mapping)
        return mapping

    def get_mappings(self, ontology_id: str) -> list[OntologyMapping]:
        return self._db.query(OntologyMapping).filter(OntologyMapping.ontology_id == ontology_id).all()

    # ── 单个 Mapping 应用 ─────────────────────────────────────────────

    def apply_mapping(self, mapping_id: str, data: list[dict]) -> dict:
        mapping = self._db.query(OntologyMapping).filter(OntologyMapping.id == mapping_id).first()
        if not mapping:
            raise ValueError(f"Mapping {mapping_id} not found")
        # PRD: Auto-infer Property Mapping from columns
        if data and len((mapping.field_mapping or {}).keys()) <= 1:
            inferred = dict(mapping.field_mapping or {})
            for col in data[0].keys():
                if col not in inferred:
                    inferred[col] = col
            mapping.field_mapping = inferred
            self._db.commit()
        entities = self._rows_to_entities(mapping, data)
        neo4j_count = self._write_neo4j(mapping.entity_class, entities)
        v1_count = self._write_v1_entities(mapping, entities)
        mapping.status = "applied"
        self._db.commit()
        return {"mapping_id": mapping_id, "entity_class": mapping.entity_class,
                "nodes_created": neo4j_count, "v1_entities_written": v1_count,
                "errors": 0, "total_rows": len(data)}

    # ── 全量构建：Entity → Relation → ChromaDB ────────────────────────

    def build_all(self, ontology_id: str) -> dict:
        from app.services.v2.dataset_service import DatasetService
        mappings = self.get_mappings(ontology_id)
        if not mappings:
            return {"error": "no mappings configured", "ontology_id": ontology_id}

        ds_svc = DatasetService(self._db)

        # Phase 1: Entity Mapping
        entity_results = []
        mapping_meta: dict[str, dict] = {}

        for m in mappings:
            if not m.curated_dataset_id:
                continue
            try:
                rows = ds_svc.preview(m.curated_dataset_id, 1, limit=10000)
            except Exception as e:
                logger.warning(f"读取数据集 {m.curated_dataset_id} 失败: {e}")
                continue

            # PRD: Auto-infer Property Mapping from columns if not set
            if rows and len((m.field_mapping or {}).keys()) <= 1:
                sample = rows[0]
                inferred_fm = dict(m.field_mapping or {})
                for col in list(sample.keys()):
                    if col not in inferred_fm:
                        # Auto-infer type and create property name
                        val = sample[col]
                        ptype = 'string'
                        if isinstance(val, (int, float)) and not isinstance(val, bool):
                            ptype = 'number'
                        elif isinstance(val, str):
                            if any(kw in col for kw in ('date','time','日期','时间','created','updated')):
                                ptype = 'timestamp'
                        inferred_fm[col] = col  # PRD: column name → property name
                m.field_mapping = inferred_fm
                self._db.commit()

            entities = self._rows_to_entities(m, rows)
            neo4j_count = self._write_neo4j(m.entity_class, entities)
            v1_count = self._write_v1_entities(m, entities)

            pk_col = (m.field_mapping or {}).get("__primary_key__")
            # 如果 PK 列不存在，自动使用第一个列（或包含 id 的列）
            if not pk_col or (rows and pk_col not in rows[0]):
                if rows:
                    cols = list(rows[0].keys())
                    # 优先找含 id 的列
                    id_cols = [c for c in cols if 'id' in c.lower() and c.lower() != 'width']
                    pk_col = id_cols[0] if id_cols else cols[0]
                else:
                    pk_col = pk_col or "id"
            entity_id_map = {
                str(row.get(pk_col, "")) if pk_col else "": e["id"]
                for row, e in zip(rows, entities)
            }
            mapping_meta[m.id] = {
                "entity_class": m.entity_class, "pk_col": pk_col,
                "rows": rows, "entity_id_map": entity_id_map,
                "columns": list(rows[0].keys()) if rows else [],
            }
            m.status = "applied"
            entity_results.append({"mapping_id": m.id, "entity_class": m.entity_class,
                                   "v1_entities_written": v1_count, "nodes_created": neo4j_count})

        self._db.commit()

        # Phase 2: Relation 推断
        relation_results = self._infer_and_write_relations(ontology_id, mappings, mapping_meta)

        # Phase 2b: Link Mapping 处理（手动配置的跨表关系）
        link_results = self._process_link_mappings(ontology_id, mapping_meta)
        relation_results.extend(link_results)

        # Phase 3: 写入 ChromaDB
        chroma_count = 0
        try:
            from app.services.v2.vector.chroma_service import ChromaService
            chroma = ChromaService()
            all_entities = []
            for m in mappings:
                if m.id not in mapping_meta:
                    continue
                meta = mapping_meta[m.id]
                for row, eid in zip(meta["rows"], meta.get("entity_id_map", {}).values()):
                    all_entities.append({"id": eid, "type": m.entity_class, "properties": row})
            if all_entities:
                chroma.upsert_entities(ontology_id, all_entities)
                chroma_count = len(all_entities)
        except Exception as e:
            logger.warning(f"ChromaDB 写入失败（非致命）: {e}")

        return {
            "ontology_id": ontology_id,
            "entity_mappings": entity_results,
            "relations_written": relation_results,
            "chroma_entities_written": chroma_count,
            "total_entities": sum(r.get("v1_entities_written", 0) for r in entity_results),
            "total_relations": sum(r.get("count", 0) for r in relation_results),
        }

    # ── Relation 推断 ───────────────────────────────────────────────

    def _infer_and_write_relations(self, ontology_id: str, mappings: list[OntologyMapping],
                                   mapping_meta: dict) -> list[dict]:
        from app.models.entity import Entity
        from app.models.relation import Relation

        results = []
        m_list = [m for m in mappings if m.id in mapping_meta]

        for i, src_m in enumerate(m_list):
            src_meta = mapping_meta[src_m.id]
            src_cols = src_meta["columns"]

            for tgt_m in m_list:
                if tgt_m.id == src_m.id:
                    continue
                tgt_meta = mapping_meta[tgt_m.id]
                tgt_class = tgt_meta["entity_class"]
                tgt_pk_col = tgt_meta["pk_col"]
                tgt_id_map = tgt_meta["entity_id_map"]

                fk_candidates = self._detect_fk_columns(
                    src_cols, tgt_class, tgt_m.entity_class,
                    src_sample_rows=src_meta.get("rows", [])
                )
                if not fk_candidates:
                    continue

                for fk_col, rel_type in fk_candidates:
                    written = 0
                    for row in src_meta["rows"]:
                        fk_val = str(row.get(fk_col, ""))
                        if not fk_val:
                            continue
                        src_pk_col = src_meta["pk_col"]
                        src_pk_val = str(row.get(src_pk_col, "")) if src_pk_col else ""
                        src_eid = src_meta["entity_id_map"].get(src_pk_val)
                        tgt_eid = tgt_id_map.get(fk_val)
                        if not src_eid or not tgt_eid:
                            continue
                        src_exists = self._db.query(Entity).filter(Entity.id == src_eid).first()
                        tgt_exists = self._db.query(Entity).filter(Entity.id == tgt_eid).first()
                        if not src_exists or not tgt_exists:
                            continue
                        rel = Relation(
                            id=str(_uuid.uuid4()), ontology_id=ontology_id,
                            source_entity=src_eid, target_entity=tgt_eid,
                            type=rel_type, properties={"fk_column": fk_col, "source": "fk_inference"},
                            confidence=0.85,
                        )
                        self._db.merge(rel)
                        written += 1
                    if written:
                        self._db.commit()
                        self._write_neo4j_relations(ontology_id, src_meta["entity_class"], tgt_class, rel_type)
                        results.append({"src": src_meta["entity_class"], "tgt": tgt_class,
                                        "rel_type": rel_type, "fk_col": fk_col, "count": written})
        return results

    # ── 工具方法 ─────────────────────────────────────────────────────

    def _rows_to_entities(self, mapping: OntologyMapping, rows: list[dict]) -> list[dict]:
        field_map = mapping.field_mapping or {}
        pk_col = field_map.get("__primary_key__")
        entities = []
        for row in rows:
            props: dict = {"ontology_id": mapping.ontology_id}
            for col, prop in field_map.items():
                if col.startswith("__"):
                    continue
                if col in row:
                    props[prop] = row[col]
            props["id"] = str(row[pk_col]) if pk_col and pk_col in row else str(_uuid.uuid4())
            entities.append(props)
        return entities

    def _write_v1_entities(self, mapping: OntologyMapping, entities: list[dict]) -> int:
        from app.models.entity import Entity
        count = 0
        try:
            for props in entities:
                eid = props["id"]
                name_cn = next((str(v) for k, v in props.items()
                               if k not in ("id", "ontology_id") and v), mapping.entity_class)
                other = {k: v for k, v in props.items() if k not in ("id", "ontology_id")}
                self._db.merge(Entity(
                    id=eid, ontology_id=mapping.ontology_id,
                    name_cn=str(name_cn)[:200], name_en=mapping.entity_class,
                    type=mapping.entity_class, properties=other,
                    confidence=mapping.confidence or 0.85,
                ))
                count += 1
            self._db.commit()
        except Exception as e:
            logger.warning(f"v1 entities 写入失败: {e}")
            self._db.rollback()
        return count

    def _write_neo4j(self, entity_class: str, entities: list[dict]) -> int:
        try:
            from app.services.v2.graph.neo4j_service import Neo4jService
            neo = Neo4jService()
            if neo.available:
                count = neo.batch_upsert_entities(entity_class, entities)
                neo.close()
                return count
        except Exception as e:
            logger.error(f"Neo4j 写入失败: {e}")
        return 0

    def _write_neo4j_relations(self, ontology_id: str, src_class: str, tgt_class: str, rel_type: str) -> None:
        from app.models.relation import Relation
        from app.models.entity import Entity
        try:
            from app.services.v2.graph.neo4j_service import Neo4jService
            neo = Neo4jService()
            if not neo.available:
                return
            rels = self._db.query(Relation).filter(
                Relation.ontology_id == ontology_id, Relation.type == rel_type,
            ).all()
            for r in rels:
                neo.upsert_relation(src_class, r.source_entity,
                                    tgt_class, r.target_entity, rel_type,
                                    props={"ontology_id": ontology_id, "confidence": r.confidence})
            neo.close()
        except Exception as e:
            logger.warning(f"Neo4j relation 写入失败（非致命）: {e}")

    # ── FK 检测（4 级策略）─────────────────────────────────────────

    def _detect_fk_columns(
        self, src_cols: list[str], tgt_entity_class: str, tgt_dataset_name: str,
        src_sample_rows: list[dict] | None = None,
    ) -> list[tuple[str, str]]:
        """多级 FK 检测: 1)标准_id 2)语义词 3)值模式 4)LLM"""
        candidates = []
        import re
        tgt_lower = tgt_entity_class.lower()
        tgt_name_lower = (tgt_dataset_name or "").lower()
        tgt_parts = [p.lower() for p in re.split(r'[_\-\s]|(?<=[a-z])(?=[A-Z])', tgt_entity_class) if p]
        tgt_parts.extend([p.lower() for p in re.split(r'[_\-\s]', tgt_name_lower) if p])

        for col in src_cols:
            col_lower = col.lower().rstrip("s")
            col_clean = re.sub(r'[\s\-]', '_', col_lower)

            is_standard_fk = col_lower.endswith("_id") or col.endswith("Id") or col.endswith("ID")
            if is_standard_fk:
                col_prefix = re.sub(r'[_]?id$', '', col_lower)
                if (col_prefix in tgt_lower or tgt_lower in col_prefix or
                    any(part in col_prefix for part in tgt_parts if len(part) > 2)):
                    rel_name = col_prefix.upper().replace("-", "_") or tgt_lower.upper()
                    rel_type = f"HAS_{rel_name}" if not rel_name.startswith("HAS_") else rel_name
                    candidates.append((col, rel_type))
                    continue

            col_words = set(re.split(r'[_\-\s]', col_clean))
            tgt_keywords = set(tgt_parts) | {tgt_lower, tgt_name_lower}
            semantic_match = {w for w in (col_words & tgt_keywords) if len(w) > 1}
            if semantic_match:
                rel_name = max(semantic_match, key=len).upper().replace("-", "_")
                rel_type = f"HAS_{rel_name}" if not rel_name.startswith("HAS_") else rel_name
                candidates.append((col, rel_type))
                continue

            if src_sample_rows and len(src_sample_rows) > 0:
                sample_vals = [str(row.get(col, "")) for row in src_sample_rows[:10] if row.get(col)]
                id_matches = [v for v in sample_vals if re.match(r'^[A-Za-z]+[-_]?\d+$', v)]
                if len(id_matches) >= 2:
                    prefixes = [re.match(r'^[A-Za-z]+', v) for v in id_matches]
                    prefixes = [m.group(0).upper() for m in prefixes if m]
                    if prefixes:
                        rel_type = f"HAS_{max(set(prefixes), key=prefixes.count)}"
                        candidates.append((col, rel_type))

        # 策略 4: LLM 辅助语义 FK 检测（前面策略没匹配时触发）
        if not candidates and src_cols:
            try:
                llm_candidates = self._llm_detect_fk(src_cols, tgt_entity_class, tgt_dataset_name)
                candidates.extend(llm_candidates)
            except Exception:
                pass

        return candidates

    def _llm_detect_fk(self, src_cols: list[str], tgt_entity_class: str, tgt_dataset_name: str) -> list[tuple[str, str]]:
        """使用用户配置的 LLM 检测中文列名→英文实体名的 FK 关系"""
        try:
            from app.services import llm_service
            from app.models.model_config import ModelConfig
            import json

            configs = self._db.query(ModelConfig).all()
            if not configs:
                return []
            mc = next((m for m in configs if m.provider == "compatible"), configs[0])
            model_name = mc.models[0] if isinstance(mc.models, list) else mc.models
            if not model_name:
                return []

            api_key = ""
            if mc.api_key_encrypted:
                try:
                    from app.services import encryption_service
                    api_key = encryption_service.decrypt(mc.api_key_encrypted)
                except Exception:
                    api_key = ""

            prompt = f"""判断以下列中哪些是外键指向目标实体。
源列名: {json.dumps(src_cols, ensure_ascii=False)}
目标实体: {tgt_entity_class}
目标数据集: {tgt_dataset_name}
规则：列名语义关联目标实体（如中文"供应商"→Supplier），或列值像ID。
返回JSON数组 [{{"column":"列名","relation_type":"HAS_XXX"}}]，无匹配返回[]。只返回JSON。"""
            raw = llm_service._call_llm(
                provider=mc.provider, api_key=api_key, api_base=mc.api_base,
                model=model_name,
                messages=[{"role": "system", "content": "输出JSON。"}, {"role": "user", "content": prompt}]
            )
            result = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(result, list):
                return [(r["column"], r["relation_type"]) for r in result if r.get("column")]
            return []
        except Exception:
            return []
    # ── Link Mapping 处理 ──

    def _process_link_mappings(self, ontology_id: str, mapping_meta: dict) -> list[dict]:
        from app.models.v2.mapping import OntologyLinkMapping, OntologyMapping as OM
        from app.models.relation import Relation

        links = self._db.query(OntologyLinkMapping).filter(
            OntologyLinkMapping.ontology_id == ontology_id,
            OntologyLinkMapping.status == "active",
        ).all()
        results = []
        for link in links:
            src_meta = tgt_meta = None
            for mid, meta in mapping_meta.items():
                m = self._db.query(OM).filter(OM.id == mid).first()
                if not m: continue
                if m.curated_dataset_id == link.src_dataset_id: src_meta = meta
                if m.curated_dataset_id == link.tgt_dataset_id: tgt_meta = meta
            if not src_meta or not tgt_meta: continue
            tgt_val_to_eid = {}
            for row, (pk_val, eid) in zip(tgt_meta["rows"], tgt_meta["entity_id_map"].items()):
                v = str(row.get(link.tgt_key, "")).strip()
                if v: tgt_val_to_eid[v] = eid
            written = 0
            for row, (src_pk_val, src_eid) in zip(src_meta["rows"], src_meta["entity_id_map"].items()):
                src_val = str(row.get(link.src_key, "")).strip()
                if not src_val or not src_eid: continue
                tgt_eid = tgt_val_to_eid.get(src_val)
                if not tgt_eid: continue
                rel = Relation(
                    id=str(_uuid.uuid4()), ontology_id=ontology_id,
                    source_entity=src_eid, target_entity=tgt_eid,
                    type=link.relation_type,
                    properties={"mapping_type": "link_mapping", "src_key": link.src_key, "tgt_key": link.tgt_key},
                    confidence=0.9,
                )
                self._db.merge(rel); written += 1
            if written:
                self._db.commit()
                self._write_neo4j_relations(ontology_id, src_meta["entity_class"], tgt_meta["entity_class"], link.relation_type)
                results.append({"src": src_meta["entity_class"], "tgt": tgt_meta["entity_class"],
                                "rel_type": link.relation_type, "src_key": link.src_key, "tgt_key": link.tgt_key,
                                "count": written})
                logger.info("Link: " + src_meta["entity_class"] + "-[" + str(link.relation_type) + "]->" + tgt_meta["entity_class"] + " " + str(written) + "条")
        return results
