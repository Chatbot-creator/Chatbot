from fastapi.testclient import TestClient
import pytest
from main import app

client = TestClient(app)

def test_create_session():
    """تست ایجاد جلسه جدید"""
    response = client.post("/api/users/session")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "message" in data
    assert "expires_at" in data
    
    # بررسی تنظیم کوکی جلسه
    assert "session_id" in response.cookies

def test_get_session_without_cookie():
    """تست دریافت جلسه بدون کوکی قبلی"""
    response = client.get("/api/users/session")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "created_at" in data
    assert "last_activity" in data
    
    # بررسی تنظیم کوکی جلسه
    assert "session_id" in response.cookies

def test_get_session_with_cookie():
    """تست دریافت جلسه با کوکی قبلی"""
    # ابتدا یک جلسه ایجاد می‌کنیم
    create_response = client.post("/api/users/session")
    session_id = create_response.cookies["session_id"]
    
    # سپس با همان کوکی درخواست می‌دهیم
    response = client.get(
        "/api/users/session", 
        cookies={"session_id": session_id}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id

def test_delete_session():
    """تست حذف جلسه"""
    # ابتدا یک جلسه ایجاد می‌کنیم
    create_response = client.post("/api/users/session")
    session_id = create_response.cookies["session_id"]
    
    # سپس آن را حذف می‌کنیم
    response = client.delete(
        "/api/users/session", 
        cookies={"session_id": session_id}
    )
    
    assert response.status_code == 204
    
    # بررسی که کوکی حذف شده باشد
    assert "session_id" not in response.cookies

def test_get_session_by_id():
    """تست دریافت جلسه با شناسه"""
    # ابتدا یک جلسه ایجاد می‌کنیم
    create_response = client.post("/api/users/session")
    session_id = create_response.json()["session_id"]
    
    # سپس آن را با شناسه دریافت می‌کنیم
    response = client.get(f"/api/users/session/{session_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id

def test_get_nonexistent_session():
    """تست دریافت جلسه غیرموجود"""
    response = client.get("/api/users/session/nonexistent-id")
    assert response.status_code == 404

def test_get_all_sessions():
    """تست دریافت لیست تمام جلسات"""
    # ابتدا چند جلسه ایجاد می‌کنیم
    client.post("/api/users/session")
    client.post("/api/users/session")
    
    # سپس لیست تمام جلسات را دریافت می‌کنیم
    response = client.get("/api/users/sessions")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # حداقل دو جلسه باید وجود داشته باشد 