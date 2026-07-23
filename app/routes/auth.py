# -*- coding: utf-8 -*-
"""用户认证API路由"""
import secrets
import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.schemas import APIResponse

router = APIRouter(prefix="/api/auth", tags=["用户认证"])
active_sessions = {}


def extract_token(request: Request, token: Optional[str] = None) -> Optional[str]:
    """从 Cookie 或 query 参数中提取 token"""
    if token:
        return token
    return request.cookies.get("session_token")


class UserRegister(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

def hash_password(password: str) -> str:
    """使用sha256哈希密码"""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"

def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    parts = password_hash.split('$')
    if len(parts) != 2:
        return False
    salt, h = parts
    return hmac.compare_digest(hashlib.sha256((salt + password).encode()).hexdigest(), h)

def create_session_token():
    """创建会话token"""
    return secrets.token_hex(32)

def get_current_user(request_token: Optional[str], db: Session) -> Optional[User]:
    """获取当前登录用户"""
    if not request_token:
        return None

    session = active_sessions.get(request_token)
    if not session:
        return None
    
    # 检查会话是否过期（24小时）
    if datetime.now() - session["created_at"] > timedelta(hours=24):
        del active_sessions[request_token]
        return None
    
    user = db.query(User).filter(User.id == session["user_id"]).first()
    if not user or not user.is_active:
        return None
    
    return user


async def require_user(request: Request, token: Optional[str] = None, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: require authenticated user, raise 401 if not logged in"""
    actual_token = extract_token(request, token)
    user = get_current_user(actual_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


@router.post("/register")
async def register(data: UserRegister, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        return APIResponse(success=False, message="用户名已存在")

    # 创建新用户
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name or data.username,
        role="user",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return APIResponse(success=True, message="注册成功", data={
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name
    })

@router.post("/login")
async def login(data: UserLogin, response: Response, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        return APIResponse(success=False, message="用户名或密码错误")

    if not user.is_active:
        return APIResponse(success=False, message="账户已被禁用")

    # 创建会话token
    token = create_session_token()
    active_sessions[token] = {
        "user_id": user.id,
        "created_at": datetime.now()
    }

    # 设置cookie
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=86400,  # 24小时
        httponly=True,
        samesite="lax"
    )

    return APIResponse(success=True, message="登录成功", data={
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role
        }
    })

@router.post("/logout")
async def logout(request: Request, token: Optional[str] = None):
    """用户登出"""
    actual_token = extract_token(request, token)
    if actual_token and actual_token in active_sessions:
        del active_sessions[actual_token]

    return APIResponse(success=True, message="已登出")

@router.get("/me")
async def get_me(request: Request, token: Optional[str] = None, db: Session = Depends(get_db)):
    """获取当前用户信息"""
    actual_token = extract_token(request, token)
    user = get_current_user(actual_token, db)
    if not user:
        return APIResponse(success=False, message="未登录")

    return APIResponse(success=True, data={
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role
    })

@router.get("/check")
async def check_login(request: Request, token: Optional[str] = None, db: Session = Depends(get_db)):
    """检查登录状态"""
    actual_token = extract_token(request, token)
    user = get_current_user(actual_token, db)
    return APIResponse(success=True, data={
        "logged_in": user is not None,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role
        } if user else None
    })
