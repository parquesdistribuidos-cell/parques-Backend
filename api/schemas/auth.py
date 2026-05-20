"""Schemas Pydantic para auth."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

    @field_validator("username")
    @classmethod
    def username_sin_espacios(cls, v):
        if " " in v:
            raise ValueError("El username no puede contener espacios")
        return v.strip()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario_id: int
    username: str


class UsuarioResponse(BaseModel):
    id: int
    username: str
    email: str
    fecha_registro: datetime

    class Config:
        from_attributes = True
