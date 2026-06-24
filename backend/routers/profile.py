"""

用户档案 API 路由

"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import UserProfile
from schemas import UserProfileCreate, UserProfileResponse, MessageResponse

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def create_or_update_profile(payload: UserProfileCreate, db: Session = Depends(get_db)):
    """创建或覆盖用户档案（幂等操作）。"""
    existing = db.query(UserProfile).filter(UserProfile.user_id == payload.user_id).first()

    if existing:
        # 更新已有记录
        for field, value in payload.model_dump().items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    profile = UserProfile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{user_id}", response_model=UserProfileResponse)
def get_profile(user_id: str, db: Session = Depends(get_db)):
    """按 user_id 查询用户档案。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="未找到该用户档案")
    return profile


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_profile(user_id: str, db: Session = Depends(get_db)):
    """删除用户档案。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="未找到该用户档案")
    db.delete(profile)
    db.commit()
    return MessageResponse(message=f"用户 {user_id} 档案已删除")
