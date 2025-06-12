from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from app.schemas.upload import UploadResponse, ProcessingStatus
from app.database import get_mongo_db
from app.services.document_processor import document_processor
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

async def process_document(file_id: str, file_path: str, filename: str, db: AsyncIOMotorDatabase):
    """Process document with FAISS indexing and embeddings"""
    try:
        await document_processor.process_document(file_path, file_id, filename, db)
    except Exception as e:
        await db["uploads"].update_one(
            {"file_id": file_id}, 
            {"$set": {"status": "failed", "error": str(e), "processed_at": datetime.utcnow()}}
        )

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
    background_tasks.add_task(process_document, file_id, file_path, file.filename, db)
    return UploadResponse(file_id=file_id, filename=file.filename, status="processing")

@router.get("/status/{file_id}", response_model=ProcessingStatus)
async def get_processing_status(file_id: str, db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    doc = await db["uploads"].find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    
    return ProcessingStatus(
        file_id=file_id,
        status=doc.get("status", "unknown"),
        processing_step=doc.get("processing_step"),
        chunks_count=doc.get("chunks_count"),
        text_length=doc.get("text_length"),
        error=doc.get("error"),
        uploaded_at=doc.get("uploaded_at"),
        processed_at=doc.get("processed_at")
    )



@router.get("/index/stats")
async def get_index_stats():
    """Get statistics about the FAISS index"""
    try:
        stats = document_processor.get_index_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}") 