from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import get_db
from app.core.security import verify_password, create_access_token
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_access_token(user.id, user.role.value)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "hotel_id": str(user.hotel_id) if user.hotel_id else None,
    }
