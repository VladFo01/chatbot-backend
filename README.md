# Knowledge Base Chatbot API

A FastAPI-based backend for the Knowledge Base Chatbot application.

## Features

- FastAPI framework with automatic API documentation
- Async MongoDB (Motor) for user, chat, and file metadata storage
- JWT authentication (register/login)
- Async file upload and background document processing
- WebSocket chat with JWT authentication and chat history
- CORS middleware
- Environment-based configuration
- Docker Compose for local development (FastAPI + MongoDB)
- Unit tests with pytest

## Project Structure

```
.
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   ├── models/
│   ├── schemas/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   └── websocket.py
├── main.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── tests/
│   └── test_auth.py
└── README.md
```

## Setup (Recommended: Docker Compose)

1. Copy `.env.example` to `.env` and fill in your secrets (or use defaults):
```bash
cp .env.example .env
```

2. Build and start all services:
```bash
docker-compose up --build
```

- FastAPI app: [http://localhost:8000](http://localhost:8000)
- MongoDB: [localhost:27017](mongodb://localhost:27017)

## Manual Setup (without Docker)

1. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Start MongoDB locally (default: `mongodb://localhost:27017`)
4. Create a `.env` file (see `.env.example`)
5. Run the app:
```bash
uvicorn main:app --reload
```

## API Endpoints

- **Auth:**
  - `POST /api/v1/auth/register` — Register a new user
  - `POST /api/v1/auth/login` — Login and get JWT token
- **File Upload:**
  - `POST /api/v1/upload/` — Upload a file (PDF, TXT, JSON, DOCX, SQL, etc.)
  - `GET /api/v1/upload/status/{file_id}` — Check processing status
- **WebSocket Chat:**
  - `ws://localhost:8000/ws/chat?token=YOUR_JWT_TOKEN` — Real-time chat (JWT required)

## API Documentation

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Running Tests

To run unit tests:
```bash
docker-compose exec app pytest
# or, if running locally
pytest
```

## Development Notes

- All files and FAISS index are stored locally (see `data/` volume)
- MongoDB is used for users, chat history, and file metadata
- WebSocket chat requires JWT token (get from login/register)
- Document processing is async (background task placeholder)
- Update CORS and secrets for production

## License

MIT 