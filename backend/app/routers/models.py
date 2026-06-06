from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.model_config import ModelConfig
from app.models.extraction_task import ExtractionTask
from app.models.user import User
from app.schemas.model_config import ModelConfigCreate, ModelConfigUpdate, ModelConfigOut
from app.services.encryption_service import encrypt, decrypt
import uuid

router = APIRouter()

@router.get("")
def list_models(db: Session = Depends(get_db), _=Depends(get_current_user)):
    configs = db.query(ModelConfig).all()
    return {"data": [ModelConfigOut.model_validate(c).model_dump() for c in configs]}

@router.post("", status_code=201)
def create_model(body: ModelConfigCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    config = ModelConfig(
        id=str(uuid.uuid4()),
        name=body.name,
        provider=body.provider,
        api_base=body.api_base,
        api_key_encrypted=encrypt(body.api_key or ""),
        models=body.models,
        created_by=current_user.id,
    )
    db.add(config); db.commit(); db.refresh(config)
    return {"data": ModelConfigOut.model_validate(config).model_dump()}

@router.get("/{model_id}")
def get_model(model_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    c = db.query(ModelConfig).filter(ModelConfig.id == model_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    return {"data": ModelConfigOut.model_validate(c).model_dump()}

@router.put("/{model_id}")
def update_model(model_id: str, body: ModelConfigUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    c = db.query(ModelConfig).filter(ModelConfig.id == model_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    if body.name is not None:
        c.name = body.name
    if body.api_key is not None:
        c.api_key_encrypted = encrypt(body.api_key)
    if body.api_base is not None:
        c.api_base = body.api_base
    if body.models is not None:
        c.models = body.models
    db.commit(); db.refresh(c)
    return {"data": ModelConfigOut.model_validate(c).model_dump()}

@router.delete("/{model_id}", status_code=204)
def delete_model(model_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    c = db.query(ModelConfig).filter(ModelConfig.id == model_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    db.query(ExtractionTask).filter(ExtractionTask.model_id == model_id).update(
        {ExtractionTask.model_id: None}, synchronize_session=False
    )
    db.delete(c)
    db.commit()

@router.post("/{model_id}/test")
def test_model(model_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    c = db.query(ModelConfig).filter(ModelConfig.id == model_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    try:
        api_key = decrypt(c.api_key_encrypted or "")
        if c.provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            model = c.models[0] if c.models else "claude-3-5-haiku-20241022"
            resp = client.messages.create(model=model, max_tokens=10, messages=[{"role": "user", "content": "ping"}])
            return {"data": {"ok": True, "response": resp.content[0].text}}
        else:
            import openai
            kwargs = {"api_key": api_key}
            if c.api_base:
                kwargs["base_url"] = c.api_base
            client = openai.OpenAI(**kwargs)
            model = c.models[0] if c.models else "gpt-4o-mini"
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=10)
            return {"data": {"ok": True, "response": resp.choices[0].message.content}}
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")
