# backend/main.py
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from backend.db import search_medicines, get_stats, rebuild_database
from backend.rag import stream_rag_response, build_vectorstore, add_document_to_vectorstore
from langchain_core.messages import HumanMessage, AIMessage
import asyncio
import pypdf
import io
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="AyuReg API", description="FastAPI Backend for AyuReg Medical Assistant")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatPayload(BaseModel):
    question: str
    chat_history: List[ChatMessage]
    role: Optional[str] = "clerk"  # Default role if not provided

@app.get("/api/stats")
def api_get_stats():
    """Returns overview statistics of the medicine database."""
    try:
        stats = get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load stats: {str(e)}")

@app.get("/api/medicines")
def api_get_medicines(
    search: Optional[str] = None,
    category: Optional[str] = None,
    classification: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    """Returns a paginated search list of medicines."""
    try:
        data, total = search_medicines(
            search_str=search,
            category=category,
            classification=classification,
            page=page,
            limit=limit
        )
        return {
            "data": data,
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database search failed: {str(e)}")

@app.post("/api/chat")
async def api_post_chat(payload: ChatPayload):
    """Handles medical RAG queries with conversation memory, returning a streamed response."""
    # Convert chat history list of dicts to LangChain Message classes
    langchain_history = []
    for msg in payload.chat_history:
        if msg.role == "user":
            langchain_history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            langchain_history.append(AIMessage(content=msg.content))
            
    # Antibiogram Stewardship Rule Check: Antibiotic usage for Viral Infection
    q_lower = payload.question.lower()
    is_viral = any(word in q_lower for word in ["viral", "virus", "flu", "cold", "influenza"])
    is_antibiotic = any(word in q_lower for word in ["antibiotic", "amoxicillin", "cipro", "penicillin", "dextrophen", "antibacterial"])
    
    antibiogram_warning = None
    if is_viral and is_antibiotic:
        antibiogram_warning = "[CLINICAL WARNING: Guidelines strictly prohibit antibiotic use for viral infections. Antimicrobial Stewardship advises symptomatic therapy (antipyretics) instead.]\n\n"

    try:
        # Get generator response stream, passing the user role directly
        token_stream = stream_rag_response(payload.question, langchain_history, role=payload.role)
        
        async def event_generator():
            if antibiogram_warning:
                yield antibiogram_warning
            for token in token_stream:
                yield token
                await asyncio.sleep(0.01)
                
        return StreamingResponse(event_generator(), media_type="text/plain")
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationError" in error_msg or "API key" in error_msg or "401" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication failed with Groq API. Please check your GROQ_API_KEY in the .env file.")
        elif "Connection refused" in error_msg or "Failed to establish a new connection" in error_msg or "APIConnectionError" in error_msg:
            raise HTTPException(status_code=503, detail="Could not connect to Groq API. Please check your internet connection.")
        raise HTTPException(status_code=500, detail=f"RAG processing failed: {error_msg}")

@app.post("/api/upload")
async def api_upload_guideline(file: UploadFile = File(...)):
    """Receives a clinical guideline file (PDF or TXT) and indexes it in the guidelines ChromaDB."""
    filename = file.filename
    
    if not (filename.endswith(".pdf") or filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported.")
        
    try:
        contents = await file.read()
        text = ""
        
        if filename.endswith(".pdf"):
            pdf_file = io.BytesIO(contents)
            reader = pypdf.PdfReader(pdf_file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        else:
            text = contents.decode("utf-8")
            
        if not text.strip():
            raise HTTPException(status_code=400, detail="The uploaded file contains no readable text.")
            
        success = add_document_to_vectorstore(text, filename)
        if not success:
            raise Exception("ChromaDB indexing failed.")
            
        return {"status": "success", "message": f"Successfully parsed and indexed guidelines from '{filename}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.post("/api/rebuild")
def api_rebuild():
    """Triggers rebuilding of SQLite index and guidelines vector database."""
    try:
        db_success = rebuild_database()
        if not db_success:
            raise Exception("CSV data file missing or import failed.")
        build_vectorstore()
        return {"status": "success", "message": "SQLite database and guidelines vector store successfully rebuilt."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
