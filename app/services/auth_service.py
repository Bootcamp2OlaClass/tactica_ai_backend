from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User

from app.utils.password import (
    hash_password,
    verify_password
)


from app.utils.jwt import(
    create_access_token
)

def register_user(
        db: Session,
        email: str,
        password: str,
        full_name: str,
):
    #check duplicate email
    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )
    
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already exists"
        )
    #Hash password
    hashed_password = hash_password(password)

    #Create new user
    user = User(
        email=email,
        password_hash=hashed_password,
        full_name=full_name
    )
    
    #save user to database
    db.add(user)
    db.commit()
    db.refresh(user)

    #create JWT token after registration
    token = create_access_token({
        "user_id": user.id,
    })

    return token

def login_user(
        db: Session,
        email: str,
        password: str
):
    
    #Find user by email
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    #User does not exist
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    #Check password
    if not verify_password(
        password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    #Create JWT token
    token = create_access_token({
        "user_id": user.id,
    })

    return token