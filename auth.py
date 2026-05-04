from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import database
import models
import os
from dotenv import load_dotenv

# .env yüklenmesi (Secret anahtarı çevre değişkeninden alınmalı, yoksa fallback)
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "b421a9d0v18p093r7f1b2v5c4f2e9d2d88v19")
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET", "r3fr3sh_s3cr3t_b421a9d_f2e9d2d88v99")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120   # 2 saat geçerli access token
REFRESH_TOKEN_EXPIRE_DAYS = 7       # 7 gün geçerli refresh token

# Bcrypt kütüphanesi yapılandırması
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Uç noktalarda token ararken Headers'taki 'Bearer' alanına baksın:
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """7 günlük Refresh Token — ayrı secret ile imzalanır."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)

def decode_refresh_token(token: str) -> str:
    """Refresh token'ı doğrular ve içindeki username'i döndürür."""
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError("Yanlış token tipi")
        username = payload.get("sub")
        if not username:
            raise ValueError("Token'da kullanıcı yok")
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş refresh token."
        )

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Geçersiz kimlik (Token)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "refresh":
            raise credentials_exception  # Refresh token'ı API girişinde ret et
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter((models.User.username == username) | (models.User.email == username)).first()
    if user is None:
        raise credentials_exception
    return user

# JWT Role Checker (Enterprise Seviye)
def role_required(allowed_roles: list[str]):
    def role_checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Oturum izni yetersiz. Gereken roller: {', '.join(allowed_roles)}")
        return current_user
    return role_checker

