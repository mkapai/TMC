"""
认证相关API路由 - 登录、注册、登出
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from database import get_db
from models import User, get_local_now
from services.login_limiter import login_limiter
from auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    get_current_active_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/auth", tags=["认证"])


def check_login_limit(ip: str) -> None:
    retry_after = login_limiter.retry_after(ip)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，IP 已临时封禁，请在 {retry_after} 秒后重试",
            headers={"Retry-After": str(retry_after)},
        )


# Pydantic 模型
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "admin123",
                "email": "admin@example.com",
                "full_name": "系统管理员"
            }
        }


class UserLogin(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "admin123"
            }
        }


class Token(BaseModel):
    access_token: str
    token_type: str


class UserInfo(BaseModel):
    id: int
    username: str
    email: Optional[str]
    full_name: Optional[str]
    avatar: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime]


class UpdateProfile(BaseModel):
    email: Optional[EmailStr] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    avatar: Optional[str] = Field(None, max_length=500, description="头像URL或Base64")


class ChangePassword(BaseModel):
    old_password: str = Field(..., min_length=6, description="旧密码")
    new_password: str = Field(..., min_length=6, description="新密码")


@router.post("/register", 
    response_model=UserInfo, 
    summary="创建新用户",
    description="""
    创建新用户账号
    
    **权限说明**:
    - 如果系统中没有任何用户，可以直接注册（第一个用户自动成为管理员）
    - 如果已有用户，则需要管理员权限才能创建新用户
    
    **请求参数**:
    - username: 用户名（3-50字符）
    - password: 密码（至少6字符）
    - email: 邮箱（可选）
    - full_name: 全名（可选）
    
    **响应**:
    返回新创建的用户信息
    """,
    responses={
        200: {
            "description": "注册成功",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "username": "admin",
                        "email": "admin@example.com",
                        "full_name": "系统管理员",
                        "is_active": True,
                        "is_admin": True,
                        "created_at": "2025-01-11T12:00:00"
                    }
                }
            }
        },
        400: {"description": "用户名或邮箱已存在"},
        401: {"description": "注册已关闭，需要管理员权限"}
    }
)
async def register(
    user_data: UserRegister, 
    db: AsyncSession = Depends(get_db)
):
    """创建新用户"""
    # 检查是否有现有用户
    result = await db.execute(select(User))
    existing_users = result.scalars().all()
    
    # 如果已有用户，检查权限
    if existing_users:
        # 这是一个内部端点，调用者需要提供有效token
        # 由于我们需要保护这个端点，让它返回401，要求先登录
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User registration is disabled. Please contact an administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # 检查邮箱是否已存在
    if user_data.email:
        result = await db.execute(select(User).where(User.email == user_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
    
    # 创建新用户
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=get_password_hash(user_data.password),
        is_admin=True  # 第一个用户自动成为管理员
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return new_user


@router.post("/login", 
    response_model=Token, 
    summary="用户登录",
    description="""
    用户登录获取访问令牌

    同一 IP 在 15 分钟内连续登录失败 5 次，将封禁登录 15 分钟。
    登录成功清除失败记录；封禁期间返回 429 和 Retry-After（秒）。
    
    **请求参数**:
    - username: 用户名
    - password: 密码
    
    **响应**:
    返回JWT访问令牌和令牌类型
    
    **使用方法**:
    1. 使用用户名和密码登录
    2. 获取返回的access_token
    3. 在后续请求中添加Header: `Authorization: Bearer <access_token>`
    
    **示例**:
    ```bash
    curl -X POST "http://localhost:9393/api/auth/login" \\
      -H "Content-Type: application/json" \\
      -d '{"username":"admin","password":"admin123"}'
    ```
    """,
    responses={
        200: {
            "description": "登录成功",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer"
                    }
                }
            }
        },
        401: {"description": "用户名或密码错误"},
        403: {"description": "用户已被禁用"},
        429: {"description": "登录失败过多，IP 已临时封禁"}
    }
)
async def login(user_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    # 由 Uvicorn 根据可信代理配置解析客户端 IP，不直接信任请求中的转发头。
    ip = request.client.host if request.client else "unknown"
    check_login_limit(ip)

    # 查找用户
    result = await db.execute(select(User).where(User.username == user_data.username))
    user = result.scalar_one_or_none()
    # 数据库查询让出执行权后，再检查是否已被其他并发请求封禁。
    check_login_limit(ip)
    
    if not user or not verify_password(user_data.password, user.password_hash):
        login_limiter.record_failure(ip)
        check_login_limit(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        login_limiter.record_failure(ip)
        check_login_limit(ip)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    login_limiter.reset(ip)

    # 更新最后登录时间
    user.last_login = get_local_now()
    await db.commit()
    
    # 创建访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserInfo, summary="获取当前用户信息")
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """获取当前登录用户的信息"""
    return current_user


@router.post("/logout", summary="用户登出")
async def logout(current_user: User = Depends(get_current_active_user)):
    """用户登出（前端需删除token）"""
    return {"message": "Successfully logged out"}


@router.put("/profile", response_model=UserInfo, summary="更新个人信息")
async def update_profile(
    profile_data: UpdateProfile,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新个人信息（邮箱、全名、头像）
    """
    try:
        # 更新邮箱
        if profile_data.email is not None:
            # 检查邮箱是否已被其他用户使用
            if profile_data.email != current_user.email:
                result = await db.execute(select(User).where(User.email == profile_data.email))
                existing_user = result.scalar_one_or_none()
                if existing_user and existing_user.id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already in use by another user"
                    )
            current_user.email = profile_data.email
        
        # 更新全名
        if profile_data.full_name is not None:
            current_user.full_name = profile_data.full_name
        
        # 更新头像
        if profile_data.avatar is not None:
            current_user.avatar = profile_data.avatar
        
        # 保存更改
        await db.commit()
        await db.refresh(current_user)
        
        return current_user
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.post("/change-password", summary="修改密码")
async def change_password(
    password_data: ChangePassword,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    修改密码
    """
    try:
        # 验证旧密码
        if not current_user.check_password(password_data.old_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Old password is incorrect"
            )
        
        # 设置新密码
        current_user.set_password(password_data.new_password)
        
        # 保存更改
        await db.commit()
        
        return {"message": "Password changed successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change password: {str(e)}"
        )

