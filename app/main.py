from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import ChatRequest, ChatResponse, HealthResponse
from app.services.rag import RAGService
from app.services.agent import AgentRouter

app = FastAPI(
    title="NusantaraCare RAG Assistant API",
    description="API Layanan Asisten Cerdas GenAI berbasis RAG untuk Panduan Operasional Internal NusantaraCare v2.0",
    version="2.0.0"
)

# CORS Middleware agar dapat diakses dari berbagai origin/client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inisialisasi Service (Lazy Singleton)
rag_service = RAGService()
agent_router = AgentRouter(rag_service)

@app.get("/", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="ok",
        version="2.0",
        service="NusantaraCare RAG Assistant"
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint utama chat assistant NusantaraCare.
    Menerima pertanyaan karyawan dan mengembalikan jawaban yang grounded,
    disertai kutipan sumber dan penanganan dokumen nonaktif v1.4 vs v2.0.
    """
    if not request.message:
        raise HTTPException(status_code=400, detail="Field 'message' (atau 'query'/'question') wajib diisi.")
    
    response = await agent_router.process_message(request.message)
    return response

# Endpoint alias untuk kompatibilitas grader/evaluator
@app.post("/query", response_model=ChatResponse)
async def query_endpoint(request: ChatRequest):
    return await chat_endpoint(request)

@app.post("/ask", response_model=ChatResponse)
async def ask_endpoint(request: ChatRequest):
    return await chat_endpoint(request)
