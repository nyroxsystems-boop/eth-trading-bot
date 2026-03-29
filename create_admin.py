#!/usr/bin/env python3
"""
Create Admin User for ETH Trading Bot Dashboard
Password is read from ADMIN_PASSWORD env var or auto-generated.
"""

import os
import secrets
from user_manager import UserManager

def main():
    print("🔐 Creating Admin User...")
    
    manager = UserManager()
    
    # Read password from env or generate a secure random one
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    generated = False
    if not admin_password:
        admin_password = secrets.token_urlsafe(16)
        generated = True
    
    admin_email = os.getenv("ADMIN_EMAIL", "admin@ethbot.com")
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    
    # Create admin user
    try:
        admin_id = manager.create_admin(
            email=admin_email,
            username=admin_username,
            password=admin_password
        )
        print(f"✅ Admin user created successfully!")
        print(f"   ID: {admin_id}")
        print(f"   Email: {admin_email}")
        print(f"   Username: {admin_username}")
        if generated:
            print(f"   Password: {admin_password}")
            print(f"\n⚠️  This is an auto-generated password. Set ADMIN_PASSWORD env var for a fixed one.")
        else:
            print(f"   Password: (from ADMIN_PASSWORD env var)")
        print(f"\n⚠️  Please change the password after first login!")
        
    except ValueError as e:
        if "already" in str(e).lower():
            print(f"ℹ️  Admin user already exists")
            print(f"   Email: {admin_email}")
            print(f"   Username: {admin_username}")
            print(f"   Password: (set via ADMIN_PASSWORD env var)")
        else:
            print(f"❌ Error: {e}")
            return 1
    
    # List all users
    print(f"\n📊 Current Users:")
    users = manager.list_users()
    for user in users:
        print(f"   - {user['username']} ({user['email']}) - {user['role']}")
    
    return 0

if __name__ == "__main__":
    exit(main())

