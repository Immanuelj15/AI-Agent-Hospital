# backend/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from backend.db import search_medicines, get_stats, rebuild_database
from backend.rag import stream_rag_response, build_vectorstore
from langchain_core.messages import HumanMessage, AIMessage
import asyncio

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
            
    try:
        # Get generator response stream
        token_stream = stream_rag_response(payload.question, langchain_history)
        
        async def event_generator():
            # Iterate over the sync generator in a thread-safe way
            for token in token_stream:
                yield token
                # Yield control to allow async tasks to run
                await asyncio.sleep(0.01)
                
        return StreamingResponse(event_generator(), media_type="text/plain")
    except Exception as e:
        error_msg = str(e)
        if "Connection refused" in error_msg or "Failed to establish a new connection" in error_msg:
            raise HTTPException(status_code=503, detail="Could not connect to Ollama. Please ensure 'ollama serve' is running.")
        raise HTTPException(status_code=500, detail=f"RAG processing failed: {error_msg}")

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
