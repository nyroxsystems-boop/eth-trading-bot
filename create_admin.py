#!/usr/bin/env python3
"""
Create Admin User for ETH Trading Bot Dashboard
"""

from user_manager import UserManager

def main():
    print("🔐 Creating Admin User...")
    
    manager = UserManager()
    
    # Create admin user
    try:
        admin_id = manager.create_admin(
            email="admin@ethbot.com",
            username="admin",
            password="admin123456"
        )
        print(f"✅ Admin user created successfully!")
        print(f"   ID: {admin_id}")
        print(f"   Email: admin@ethbot.com")
        print(f"   Username: admin")
        print(f"   Password: admin123456")
        print(f"\n⚠️  Please change the password after first login!")
        
    except ValueError as e:
        if "already" in str(e).lower():
            print(f"ℹ️  Admin user already exists")
            print(f"   Email: admin@ethbot.com")
            print(f"   Username: admin")
            print(f"   Password: admin123456")
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
