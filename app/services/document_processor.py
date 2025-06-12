import os
import asyncio
from typing import List, Dict, Any
from pathlib import Path
import logging

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.document import Document
import faiss
import numpy as np
import pickle
import PyPDF2
from docx import Document as DocxDocument
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DocumentProcessor:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            logger.warning("OpenAI API key not provided. Document processing will be limited.")
            self.embeddings = None
        else:
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                model="text-embedding-ada-002"
            )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.faiss_index_path = "data/faiss_index"
        self.documents_path = "data/documents.pkl"
        
        # Ensure directories exist
        os.makedirs(self.faiss_index_path, exist_ok=True)
        os.makedirs(os.path.dirname(self.documents_path), exist_ok=True)
        
        # Initialize or load FAISS index
        self.index = None
        self.documents = []
        self._load_index()

    def _load_index(self):
        """Load existing FAISS index and documents"""
        try:
            index_file = os.path.join(self.faiss_index_path, "index.faiss")
            if os.path.exists(index_file):
                self.index = faiss.read_index(index_file)
                logger.info(f"Loaded FAISS index with {self.index.ntotal} vectors")
            else:
                # Create new index (768 dimensions for OpenAI embeddings)
                self.index = faiss.IndexFlatL2(1536)  # text-embedding-ada-002 dimension
                logger.info("Created new FAISS index")
                
            if os.path.exists(self.documents_path):
                with open(self.documents_path, 'rb') as f:
                    self.documents = pickle.load(f)
                logger.info(f"Loaded {len(self.documents)} document chunks")
            else:
                self.documents = []
                
        except Exception as e:
            logger.error(f"Error loading FAISS index: {e}")
            self.index = faiss.IndexFlatL2(1536)
            self.documents = []

    def _save_index(self):
        """Save FAISS index and documents"""
        try:
            index_file = os.path.join(self.faiss_index_path, "index.faiss")
            faiss.write_index(self.index, index_file)
            
            with open(self.documents_path, 'wb') as f:
                pickle.dump(self.documents, f)
                
            logger.info(f"Saved FAISS index with {self.index.ntotal} vectors")
        except Exception as e:
            logger.error(f"Error saving FAISS index: {e}")

    def extract_text_from_file(self, file_path: str) -> str:
        """Extract text from various file formats"""
        file_path = Path(file_path)
        text = ""
        
        try:
            if file_path.suffix.lower() == '.pdf':
                text = self._extract_from_pdf(file_path)
            elif file_path.suffix.lower() in ['.docx', '.doc']:
                text = self._extract_from_docx(file_path)
            elif file_path.suffix.lower() == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                logger.warning(f"Unsupported file format: {file_path.suffix}")
                return ""
                
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return ""
            
        return text

    def _extract_from_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file"""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
        except Exception as e:
            logger.error(f"Error reading PDF {file_path}: {e}")
        return text

    def _extract_from_docx(self, file_path: Path) -> str:
        """Extract text from DOCX file"""
        text = ""
        try:
            doc = DocxDocument(file_path)
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
        except Exception as e:
            logger.error(f"Error reading DOCX {file_path}: {e}")
        return text

    async def process_document(self, file_path: str, file_id: str, filename: str, db: AsyncIOMotorDatabase):
        """Process a document: extract text, split, embed, and index"""
        try:
            logger.info(f"Starting processing for {filename}")
            
            # Update status to processing
            await db["uploads"].update_one(
                {"file_id": file_id},
                {"$set": {"status": "processing", "processing_step": "extracting_text"}}
            )
            
            # Extract text
            text = self.extract_text_from_file(file_path)
            if not text.strip():
                await db["uploads"].update_one(
                    {"file_id": file_id},
                    {"$set": {"status": "failed", "error": "No text could be extracted"}}
                )
                return
            
            # Update status
            await db["uploads"].update_one(
                {"file_id": file_id},
                {"$set": {"processing_step": "splitting_text"}}
            )
            
            # Split text into chunks
            documents = self.text_splitter.create_documents(
                [text],
                metadatas=[{
                    "file_id": file_id,
                    "filename": filename,
                    "source": file_path
                }]
            )
            
            # Update status
            await db["uploads"].update_one(
                {"file_id": file_id},
                {"$set": {"processing_step": "generating_embeddings"}}
            )
            
            # Generate embeddings
            texts = [doc.page_content for doc in documents]
            embeddings = await self._generate_embeddings_async(texts)
            
            # Update status
            await db["uploads"].update_one(
                {"file_id": file_id},
                {"$set": {"processing_step": "indexing"}}
            )
            
            # Add to FAISS index
            self._add_to_index(documents, embeddings)
            
            # Save index
            self._save_index()
            
            # Update status to completed
            await db["uploads"].update_one(
                {"file_id": file_id},
                {
                    "$set": {
                        "status": "processed",
                        "processing_step": "completed",
                        "chunks_count": len(documents),
                        "text_length": len(text)
                    }
                }
            )
            
            logger.info(f"Successfully processed {filename} - {len(documents)} chunks created")
            
        except Exception as e:
            logger.error(f"Error processing document {filename}: {e}")
            await db["uploads"].update_one(
                {"file_id": file_id},
                {"$set": {"status": "failed", "error": str(e)}}
            )

    async def _generate_embeddings_async(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings asynchronously"""
        if not self.embeddings:
            raise ValueError("OpenAI API key not configured. Cannot generate embeddings.")
        
        # OpenAI embeddings don't have native async support in langchain yet
        # So we'll run it in a thread pool
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self.embeddings.embed_documents, texts
        )
        return embeddings

    def _add_to_index(self, documents: List[Document], embeddings: List[List[float]]):
        """Add documents and embeddings to FAISS index"""
        # Convert embeddings to numpy array
        embeddings_array = np.array(embeddings).astype('float32')
        
        # Add to FAISS index
        self.index.add(embeddings_array)
        
        # Store document metadata
        for doc in documents:
            self.documents.append({
                "content": doc.page_content,
                "metadata": doc.metadata
            })

    async def search_similar_documents(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar documents using FAISS"""
        try:
            # Generate embedding for query
            query_embedding = await self._generate_embeddings_async([query])
            query_vector = np.array(query_embedding).astype('float32')
            
            # Search in FAISS index
            scores, indices = self.index.search(query_vector, k)
            
            # Get matching documents
            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(self.documents):
                    doc = self.documents[idx]
                    results.append({
                        "content": doc["content"],
                        "metadata": doc["metadata"],
                        "similarity_score": float(score),
                        "rank": i + 1
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the FAISS index"""
        return {
            "total_vectors": self.index.ntotal,
            "total_documents": len(self.documents),
            "index_dimension": self.index.d,
            "index_type": type(self.index).__name__
        }

# Global instance
document_processor = DocumentProcessor() 