from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import api_v1_router
from app.database import get_mongo_db
from app.websocket import websocket_endpoint
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.services.document_processor import document_processor

app = FastAPI(
    title="Knowledge Base Chatbot API",
    description="Backend API for the Knowledge Base Chatbot application",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Knowledge Base Chatbot API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    await websocket_endpoint(websocket, db)

@app.post("/admin/clear_index")
def clear_index():
    document_processor.clear_index()
    return {"status": "success", "message": "FAISS index and document list cleared."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)