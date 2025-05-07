from fastapi.testclient import TestClient
import pytest
from main import app

client = TestClient(app)

def test_register_user():
    """تست ثبت‌نام کاربر جدید"""
    user_data = {
        "username": "testuser",
        "password": "testpassword",
        "is_active": True
    }
    response = client.post("/api/users/register", json=user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == user_data["username"]
    assert "id" in data
    assert "message" in data
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_register_duplicate_user():
    """تست ثبت‌نام کاربر تکراری"""
    # ابتدا یک کاربر ثبت‌نام می‌کنیم
    user_data = {
        "username": "duplicateuser",
        "password": "testpassword",
        "is_active": True
    }
    client.post("/api/users/register", json=user_data)
    
    # سپس همان کاربر را دوباره ثبت‌نام می‌کنیم
    response = client.post("/api/users/register", json=user_data)
    assert response.status_code == 400
    assert "detail" in response.json()

def test_login_user():
    """تست ورود کاربر"""
    # ابتدا یک کاربر ثبت‌نام می‌کنیم
    user_data = {
        "username": "loginuser",
        "password": "testpassword",
        "is_active": True
    }
    client.post("/api/users/register", json=user_data)
    
    # سپس با آن وارد می‌شویم
    login_data = {
        "username": "loginuser",
        "password": "testpassword"
    }
    response = client.post("/api/users/login", data=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["username"] == user_data["username"]
    
    # بررسی کوکی جلسه
    assert "session_id" in response.cookies

def test_get_me_with_token():
    """تست دریافت اطلاعات کاربر با توکن"""
    # ابتدا یک کاربر ثبت‌نام می‌کنیم
    user_data = {
        "username": "meuser",
        "password": "testpassword",
        "is_active": True
    }
    register_response = client.post("/api/users/register", json=user_data)
    token = register_response.json()["access_token"]
    
    # سپس اطلاعات خود را دریافت می‌کنیم
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user_data["username"]

def test_logout():
    """تست خروج کاربر"""
    # ابتدا یک کاربر ثبت‌نام و وارد می‌کنیم
    user_data = {
        "username": "logoutuser",
        "password": "testpassword",
        "is_active": True
    }
    client.post("/api/users/register", json=user_data)
    
    login_data = {
        "username": "logoutuser",
        "password": "testpassword"
    }
    login_response = client.post("/api/users/login", data=login_data)
    cookies = login_response.cookies
    
    # سپس خارج می‌شویم
    response = client.post("/api/users/logout", cookies=cookies)
    assert response.status_code == 200
    assert "message" in response.json()
    
    # بررسی حذف کوکی
    assert "session_id" not in response.cookies 