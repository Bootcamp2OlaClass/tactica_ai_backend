from pydantic import BaseModel

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    email_verified: bool

    class Config:
        from_attributes = True

class PasswordResetRequestSchema(BaseModel):
    email: str

class PasswordResetConfirmSchema(BaseModel):
    token: str
    new_password: str

class EmailVerificationConfirmSchema(BaseModel):
    token: str

class MessageResponse(BaseModel):
    message: str
