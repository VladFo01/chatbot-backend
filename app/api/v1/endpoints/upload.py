from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from app.schemas.upload import UploadResponse, ProcessingStatus
from app.database import get_mongo_db
from motor.motor_asyncio import AsyncIOMotorDatabase
from uuid import uuid4
import os
from datetime import datetime

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def save_file(file: UploadFile, file_id: str) -> str:
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    return file_path

async def process_document(file_id: str, file_path: str, db: AsyncIOMotorDatabase):
    # Placeholder for async document processing (embeddings, indexing, etc.)
    await db["uploads"].update_one({"file_id": file_id}, {"$set": {"status": "processed", "processed_at": datetime.utcnow()}}, upsert=True)

@router.post("/", response_model=UploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db)
):
    file_id = str(uuid4())
    file_path = await save_file(file, file_id)
    await db["uploads"].insert_one({
        "file_id": file_id,
        "filename": file.filename,
        "path": file_path,
        "status": "processing",
        "uploaded_at": datetime.utcnow()
    })
    background_tasks.add_task(process_document, file_id, file_path, db)
    return UploadResponse(file_id=file_id, filename=file.filename, status="processing")

@router.get("/status/{file_id}", response_model=ProcessingStatus)
async def get_processing_status(file_id: str, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    doc = await db["uploads"].find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    return ProcessingStatus(file_id=file_id, status=doc.get("status", "unknown"), detail=None) 