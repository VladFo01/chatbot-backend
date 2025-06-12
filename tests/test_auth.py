import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from main import app
from app.database import get_mongo_db

# Global test database to persist data between calls
test_users = {}

# Mock the database dependency
def get_mock_mongo_db():
    mock_db = MagicMock()
    # Create a proper mock for the users collection
    mock_users_collection = MagicMock()
    
    async def mock_find_one(query):
        email = query.get("email")
        return test_users.get(email)
    
    async def mock_insert_one(user_data):
        # Store the user for later retrieval
        test_users[user_data["email"]] = user_data
        return MagicMock(inserted_id="test_id")
    
    mock_users_collection.find_one = mock_find_one
    mock_users_collection.insert_one = mock_insert_one
    
    # Make db["users"] return the mocked collection
    mock_db.__getitem__ = MagicMock(return_value=mock_users_collection)
    return mock_db

# Override the dependency
app.dependency_overrides[get_mongo_db] = get_mock_mongo_db

client = TestClient(app)

@pytest.fixture(scope="module")
def test_user():
    return {"email": "testuser@example.com", "password": "testpassword"}

def test_register_and_login(test_user):
    # Register
    response = client.post("/api/v1/auth/register", json=test_user)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    # Login
    response = client.post(
        "/api/v1/auth/login",
        json=test_user
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data 