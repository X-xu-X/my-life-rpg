"""锚点路由：锚点库查询 + 校准（用户可见可校准，PRD 4.4 节）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AnchorCalibrateIn
from app.services import anchor_service

router = APIRouter()


@router.get("/anchors")
def list_anchors(db: Session = Depends(get_db)):
    """锚点库列表（含基准值、校准值、科学依据）。"""
    anchors = anchor_service.list_anchors(db)
    return [
        {
            "id": a.id,
            "name": a.name,
            "description": a.description,
            "category": a.category,
            "target_attribute": a.target_attribute,
            "base_value": a.base_value,
            "unit": a.unit,
            "base_delta": a.base_delta,
            "evidence": a.evidence,
            "is_builtin": a.is_builtin,
            "calibrated_value": a.calibrated_value,
        }
        for a in anchors
    ]


@router.post("/anchors/{anchor_id}/calibrate")
def calibrate(anchor_id: int, body: AnchorCalibrateIn, db: Session = Depends(get_db)):
    """校准锚点基准量（校准后 AI 判定随之调整）。calibrated_value=null 恢复默认。"""
    anchor = anchor_service.calibrate_anchor(db, anchor_id, body.calibrated_value)
    if anchor is None:
        raise HTTPException(status_code=404, detail="锚点不存在")
    return {
        "id": anchor.id,
        "name": anchor.name,
        "base_value": anchor.base_value,
        "calibrated_value": anchor.calibrated_value,
    }
