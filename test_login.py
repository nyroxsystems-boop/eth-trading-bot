#!/usr/bin/env python
"""
Test script to debug the login endpoint issue
"""
import sys
sys.path.insert(0, '/Users/xaaronvx/Desktop/ethbot_code')

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from user_manager import UserManager

app = FastAPI()
user_mgr = UserManager()

class UserLogin(BaseModel):
    email_or_username: str
    password: str

class AuthResponse(BaseModel):
    user_id: int
    email: str
    username: str
    role: str
    token: str

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: UserLogin):
    """Login user"""
    try:
        print(f"Login attempt for: {request.email_or_username}")
        result = user_mgr.login(request.email_or_username, request.password)
        
        if not result:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        print(f"Login successful: {result}")
        return AuthResponse(**result)
        
    except ValueError as e:
        print(f"ValueError: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting test server on port 3001...")
    uvicorn.run(app, host="0.0.0.0", port=3001)
