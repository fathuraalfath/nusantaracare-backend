from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

class ChatRequest(BaseModel):
    message: Optional[str] = Field(None, description="Pertanyaan karyawan terkait panduan operasional")
    query: Optional[str] = Field(None, description="Alias query untuk fleksibilitas testing")
    question: Optional[str] = Field(None, description="Alias question untuk fleksibilitas testing")

    @model_validator(mode="before")
    @classmethod
    def populate_message(cls, data: dict):
        if isinstance(data, dict):
            if not data.get("message"):
                # ponytail: reuse query or question if message is omitted
                if data.get("query"):
                    data["message"] = data["query"]
                elif data.get("question"):
                    data["message"] = data["question"]
        return data


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Jawaban final berbasis dokumen NusantaraCare v2.0")
    confidence_label: Literal["high", "medium", "low"] = Field(..., description="Tingkat keyakinan sistem")
    reason_code: str = Field(..., description="Alasan sistem (misal: answered, no_relevant_context, prompt_injection, out_of_scope)")

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0"
    service: str = "NusantaraCare RAG Assistant"
