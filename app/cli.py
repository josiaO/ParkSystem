from __future__ import annotations

import argparse
import getpass
from sqlalchemy import select

from .api_main import ensure_roles
from .config import settings
from .db import SessionLocal, ensure_schema
from .models import Role, User, UserRole
from .security import hash_password
from .services.bootstrap import reset_bootstrap_admin


def create_admin():
    ensure_schema()
    with SessionLocal() as db:
        ensure_roles(db)
        username=input("Admin username: ").strip()
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit("User already exists")
        full_name=input("Full name: ").strip()
        password=getpass.getpass("Password: ")
        confirm=getpass.getpass("Confirm: ")
        if password != confirm or len(password) < 10:
            raise SystemExit("Passwords must match and be at least 10 characters")
        user=User(username=username, full_name=full_name, password_hash=hash_password(password))
        db.add(user); db.flush()
        admin=db.scalar(select(Role).where(Role.name == "Admin"))
        db.add(UserRole(user_id=user.id, role_id=admin.id))
        db.commit()
        print("Admin created")


def reset_admin():
    ensure_schema()
    with SessionLocal() as db:
        ensure_roles(db)
        action = reset_bootstrap_admin(db)
    print(f"Admin {action}: {settings.bootstrap_username} / {settings.bootstrap_password}")


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command", required=True)
    sub.add_parser("create-admin")
    sub.add_parser("reset-admin")
    args=p.parse_args()
    if args.command == "create-admin": create_admin()
    elif args.command == "reset-admin": reset_admin()


if __name__ == "__main__": main()
