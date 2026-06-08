"""PRD v1.1 Ontology Logic & Actions API"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.v2.logic import OntologyLogicRule, OntologyStateMachine
from app.models.v2.action import OntologyActionType, OntologyActionRun

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Logic Rules ─────────────────────────────────────────────────

class LogicRuleCreate(BaseModel):
    name: str
    logic_type: str
    description: str = ""
    target_entity_type: Optional[str] = None
    expression: dict = {}
    source_type: Optional[str] = None
    severity: str = "info"
    enabled: bool = True


@router.get("/{ontology_id}/logic")
def list_logic_rules(ontology_id: str, logic_type: str = "", db: Session = Depends(get_db)):
    q = db.query(OntologyLogicRule).filter(OntologyLogicRule.ontology_id == ontology_id)
    if logic_type:
        q = q.filter(OntologyLogicRule.logic_type == logic_type)
    rules = q.order_by(OntologyLogicRule.created_at.desc()).all()
    return [{"id": r.id, "name": r.name, "logic_type": r.logic_type, "description": r.description,
             "target_entity_type": r.target_entity_type, "severity": r.severity, "enabled": r.enabled,
             "status": r.status, "version": r.version, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rules]


@router.post("/{ontology_id}/logic", status_code=201)
def create_logic_rule(ontology_id: str, body: LogicRuleCreate, db: Session = Depends(get_db)):
    rule = OntologyLogicRule(
        ontology_id=ontology_id, name=body.name, logic_type=body.logic_type,
        description=body.description, target_entity_type=body.target_entity_type,
        expression=body.expression, source_type=body.source_type,
        severity=body.severity, enabled=body.enabled,
    )
    db.add(rule); db.commit(); db.refresh(rule)
    return {"id": rule.id, "name": rule.name, "status": rule.status}


@router.put("/{ontology_id}/logic/{rule_id}")
def update_logic_rule(ontology_id: str, rule_id: str, body: LogicRuleCreate, db: Session = Depends(get_db)):
    rule = db.query(OntologyLogicRule).filter(
        OntologyLogicRule.id == rule_id, OntologyLogicRule.ontology_id == ontology_id
    ).first()
    if not rule:
        raise HTTPException(404, "Logic rule not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": rule.id, "status": "updated"}


@router.delete("/{ontology_id}/logic/{rule_id}")
def delete_logic_rule(ontology_id: str, rule_id: str, db: Session = Depends(get_db)):
    rule = db.query(OntologyLogicRule).filter(
        OntologyLogicRule.id == rule_id, OntologyLogicRule.ontology_id == ontology_id
    ).first()
    if not rule:
        raise HTTPException(404, "Logic rule not found")
    db.delete(rule); db.commit()
    return {"status": "deleted"}


# ── Logic: Discovery ────────────────────────────────────────────

@router.post("/{ontology_id}/logic/discover")
def discover_logic_rules(ontology_id: str, db: Session = Depends(get_db)):
    """发现 Logic Rules（同步写入 v2 + v1 表，供前端 LogicTab 读取）"""
    from app.services.v2.mapping.mapping_service import MappingService
    from app.models.logic import LogicRule as LogicRuleV1
    import uuid
    svc = MappingService(db)
    mappings = svc.get_mappings(ontology_id)
    created = []
    for m in mappings:
        name = f"Mapping: {m.entity_class}"
        exists = db.query(OntologyLogicRule).filter(
            OntologyLogicRule.ontology_id == ontology_id,
            OntologyLogicRule.name == name,
        ).first()
        if not exists:
            db.add(OntologyLogicRule(
                ontology_id=ontology_id, name=name, logic_type="mapping",
                description=f"Entity Mapping: {m.entity_class}",
                target_entity_type=m.entity_class,
                expression={"field_mapping": m.field_mapping},
                source_type="mapping", severity="info",
            ))
            # v1 表（前端 LogicTab 读取）
            if not db.query(LogicRuleV1).filter(
                LogicRuleV1.ontology_id == ontology_id, LogicRuleV1.name_cn == name,
            ).first():
                db.add(LogicRuleV1(
                    id=str(uuid.uuid4()), ontology_id=ontology_id,
                    name_cn=name, name_en=name,
                    description=f"Entity Mapping: {m.entity_class}",
                    formula=f"mapping:{m.entity_class}", confidence=0.85,
                    enabled=True, status="draft",
                    linked_entities=[m.entity_class],
                ))
            created.append(name)
    # PRD ④: 额外发现 Quality/Validation/State/Security/Automation 规则
    quality_rules = [
        ("Validation: 数据完整性检查", "validation", "完整性: 检查必填字段和 null 率", 0.8),
        ("Quality: 数据质量监控", "validation", "质量: 监控重复率和异常值", 0.75),
        ("Business: 业务规则推导", "business", "业务: 基于领域知识的业务规则", 0.7),
        ("Inference: 图推导关系", "inference", "推导: 基于实体关系推导隐含关联", 0.7),
        ("State: 状态流转规则", "state", "状态: 数据状态流转和审核流程", 0.75),
        ("Security: 访问控制", "security", "安全: 基于角色限制读写权限", 0.85),
        ("Automation: 自动同步触发", "automation", "自动化: Curated 审批通过后触发增量更新", 0.9),
    ]
    for qname, qtype, qdesc, qconf in quality_rules:
        if not db.query(LogicRuleV1).filter(
            LogicRuleV1.ontology_id == ontology_id, LogicRuleV1.name_cn == qname,
        ).first():
            db.add(LogicRuleV1(
                id=str(uuid.uuid4()), ontology_id=ontology_id,
                name_cn=qname, name_en=qname.replace(": ", "_"),
                description=qdesc, formula=qtype, confidence=qconf,
                enabled=True, status="draft",
            ))
    db.commit()
    total_v1 = db.query(LogicRuleV1).filter(LogicRuleV1.ontology_id == ontology_id).count()
    total_v2 = db.query(OntologyLogicRule).filter(OntologyLogicRule.ontology_id == ontology_id).count()
    return {"discovered": len(created), "total_v2": total_v2, "total_v1": total_v1}


# ── State Machines ──────────────────────────────────────────────

@router.get("/{ontology_id}/state-machines")
def list_state_machines(ontology_id: str, db: Session = Depends(get_db)):
    machines = db.query(OntologyStateMachine).filter(
        OntologyStateMachine.ontology_id == ontology_id
    ).all()
    return [{"id": m.id, "entity_type_name": m.entity_type_name, "state_property": m.state_property,
             "states": m.states, "transitions": m.transitions} for m in machines]


# ── Action Types ────────────────────────────────────────────────

class ActionTypeCreate(BaseModel):
    name: str
    action_category: str
    description: str = ""
    target_entity_type: Optional[str] = None
    parameters: list = []
    submission_criteria: Optional[list] = None
    effects: list = []
    side_effects: Optional[list] = None
    permission_rules: Optional[list] = None
    enabled: bool = True


@router.get("/{ontology_id}/actions")
def list_action_types(ontology_id: str, category: str = "", db: Session = Depends(get_db)):
    q = db.query(OntologyActionType).filter(OntologyActionType.ontology_id == ontology_id)
    if category:
        q = q.filter(OntologyActionType.action_category == category)
    actions = q.order_by(OntologyActionType.created_at.desc()).all()
    return [{"id": a.id, "name": a.name, "action_category": a.action_category,
             "description": a.description, "target_entity_type": a.target_entity_type,
             "enabled": a.enabled, "status": a.status, "version": a.version,
             "created_at": a.created_at.isoformat() if a.created_at else None} for a in actions]


@router.post("/{ontology_id}/actions", status_code=201)
def create_action_type(ontology_id: str, body: ActionTypeCreate, db: Session = Depends(get_db)):
    act = OntologyActionType(
        ontology_id=ontology_id, name=body.name, action_category=body.action_category,
        description=body.description, target_entity_type=body.target_entity_type,
        parameters=body.parameters, submission_criteria=body.submission_criteria,
        effects=body.effects, side_effects=body.side_effects,
        permission_rules=body.permission_rules, enabled=body.enabled,
    )
    db.add(act); db.commit(); db.refresh(act)
    return {"id": act.id, "name": act.name, "status": act.status}


@router.post("/{ontology_id}/actions/discover")
def discover_actions(ontology_id: str, db: Session = Depends(get_db)):
    """发现 Actions（同步写入 v2 + v1 表，供前端 ActionsTab 读取）"""
    from app.services.v2.mapping.mapping_service import MappingService
    from app.models.action import Action as ActionV1
    import uuid
    svc = MappingService(db)
    mappings = svc.get_mappings(ontology_id)
    created = []
    for m in mappings:
        name = f"Create {m.entity_class}"
        if not db.query(OntologyActionType).filter(
            OntologyActionType.ontology_id == ontology_id,
            OntologyActionType.name == name,
        ).first():
            db.add(OntologyActionType(
                ontology_id=ontology_id, name=name, action_category="crud",
                description=f"创建 {m.entity_class} 实体",
                target_entity_type=m.entity_class,
                parameters=[{"name": "data", "type": "object", "required": True}],
                effects=[{"action": "create_node", "entity_type": m.entity_class}],
            ))
            if not db.query(ActionV1).filter(
                ActionV1.ontology_id == ontology_id, ActionV1.name_cn == name,
            ).first():
                db.add(ActionV1(
                    id=str(uuid.uuid4()), ontology_id=ontology_id,
                    name_cn=name, name_en=name,
                    description=f"创建 {m.entity_class}", confidence=0.85,
                    enabled=True, status="draft",
                    linked_entities=[m.entity_class],
                ))
            created.append(name)
    # PRD ⑤: Review/Repair 动作类型
    for aname, acat, adesc, aconf in [
        ("Link: 关系维护", "link", "维护实体间的关系链接", 0.8),
        ("State: 状态流转", "state_transition", "执行实体状态迁移操作", 0.8),
        ("Review: 人工审核确认", "review", "对 pending_review 数据进行人工审核", 0.85),
        ("Repair: 数据质量修复", "repair", "修复质量报告中标记的异常数据", 0.75),
        ("Writeback: 外部写回", "writeback", "将审核通过的数据写回外部系统", 0.7),
    ]:
        if not db.query(ActionV1).filter(
            ActionV1.ontology_id == ontology_id, ActionV1.name_cn == aname,
        ).first():
            db.add(ActionV1(
                id=str(uuid.uuid4()), ontology_id=ontology_id,
                name_cn=aname, name_en=aname.replace(": ","_"),
                description=adesc, confidence=aconf,
                enabled=True, status="draft",
            ))
    db.commit()
    tv1 = db.query(ActionV1).filter(ActionV1.ontology_id == ontology_id).count()
    tv2 = db.query(OntologyActionType).filter(OntologyActionType.ontology_id == ontology_id).count()
    return {"discovered": len(created), "total_v2": tv2, "total_v1": tv1}


@router.delete("/{ontology_id}/actions/{action_id}")
def delete_action_type(ontology_id: str, action_id: str, db: Session = Depends(get_db)):
    act = db.query(OntologyActionType).filter(
        OntologyActionType.id == action_id, OntologyActionType.ontology_id == ontology_id
    ).first()
    if not act:
        raise HTTPException(404, "Action type not found")
    db.delete(act); db.commit()
    return {"status": "deleted"}


# ── Action Runs ─────────────────────────────────────────────────

@router.get("/{ontology_id}/action-runs")
def list_action_runs(ontology_id: str, limit: int = 20, db: Session = Depends(get_db)):
    runs = db.query(OntologyActionRun).filter(
        OntologyActionRun.ontology_id == ontology_id
    ).order_by(OntologyActionRun.started_at.desc()).limit(limit).all()
    return [{"id": r.id, "action_type_id": r.action_type_id, "status": r.status,
             "target_object_id": r.target_object_id, "error": r.error,
             "started_at": r.started_at.isoformat() if r.started_at else None} for r in runs]
