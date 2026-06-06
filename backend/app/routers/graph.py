from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.entity import Entity
from app.models.relation import Relation
from app.models.ontology import OntologyProject

router = APIRouter()

@router.get("")
def get_graph(ontology_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    project = db.query(OntologyProject).filter(OntologyProject.id == ontology_id).first()
    if not project:
        raise HTTPException(404, "Ontology not found")

    entities = db.query(Entity).filter(Entity.ontology_id == ontology_id).all()
    relations = db.query(Relation).filter(Relation.ontology_id == ontology_id).all()

    nodes = [
        {
            "data": {
                "id": e.id,
                "label": e.name_cn,
                "name_en": e.name_en,
                "name_abbr": e.name_abbr,
                "type": e.type,
                "confidence": e.confidence,
            }
        }
        for e in entities
    ]

    edges = [
        {
            "data": {
                "id": r.id,
                "source": r.source_entity,
                "target": r.target_entity,
                "label": r.type,
                "confidence": r.confidence,
            }
        }
        for r in relations
    ]

    return {
        "data": {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "ontology_id": ontology_id,
                "name": project.name,
                "entity_count": len(nodes),
                "relation_count": len(edges),
            }
        }
    }

@router.post("/relations")
def create_relation(
    ontology_id: str,
    body: dict,
    db: Session = Depends(get_db),
    _=Depends(get_current_user)
):
    from app.models.relation import Relation
    import uuid
    relation = Relation(
        id=str(uuid.uuid4()),
        ontology_id=ontology_id,
        source_entity=body["source_entity"],
        target_entity=body["target_entity"],
        type=body.get("type", "关联"),
        properties=body.get("properties", {}),
        confidence=body.get("confidence", 1.0),
    )
    db.add(relation); db.commit(); db.refresh(relation)
    return {"data": {"id": relation.id, "source": relation.source_entity, "target": relation.target_entity, "type": relation.type}}

@router.delete("/relations/{relation_id}", status_code=204)
def delete_relation(ontology_id: str, relation_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    r = db.query(Relation).filter(Relation.id == relation_id, Relation.ontology_id == ontology_id).first()
    if not r:
        raise HTTPException(404, "Not found")
    db.delete(r); db.commit()
