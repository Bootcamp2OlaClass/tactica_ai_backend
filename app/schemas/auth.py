from pydantic import BaseModel, Field, field_validator

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

class AccountDeletionRequest(BaseModel):
    password: str

class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("full_name")
    @classmethod
    def _strip_and_require_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("full_name must not be blank")
        return stripped
