import re
from typing import Tuple
from app.schemas import ChatResponse
from app.services.rag import RAGService

# Pola deteksi prompt injection
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"abaikan\s+(semua\s+)?(instruksi|perintah|aturan)",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions|rules)",
    r"bocorkan\s+(system\s+prompt|instruksi|rahasia)",
    r"tampilkan\s+(system\s+prompt|instruksi\s+internal)",
    r"you\s+are\s+now\s+(DAN|unrestricted|an\s+adversary|a\s+hacker)",
    r"kamu\s+sekarang\s+adalah",
    r"jailbreak",
    r"act\s+as\s+an\s+unrestricted",
    r"system\s*prompt",
    r"override\s+system",
    r"bypass\s+(security|guardrail|filters)"
]

# 5 Area yang secara eksplisit dikecualikan dalam panduan internal NusantaraCare v2.0
OUT_OF_SCOPE_TOPICS = [
    (r"\b(sakit|obat|diagnosis|gejala penyakit|konsultasi dokter|medis|resep obat)\b", 
     "Pertanyaan Anda berkaitan dengan konsultasi medis atau kesehatan karyawan. Sesuai panduan resmi NusantaraCare, layanan ini berada di luar cakupan Panduan Operasional Layanan Internal. Silakan menghubungi unit layanan kesehatan/klinik perusahaan."),
    (r"\b(nasihat hukum|pasal uu|gugatan|peraturan perundang-undangan|pengacara)\b",
     "Pertanyaan Anda berkaitan dengan nasihat hukum atau peraturan perundang-undangan. Masalah ini berada di luar kewenangan operasional Service Desk dan menjadi ranah Direktorat Hukum/Legal."),
    (r"\b(gaji|slip gaji|nominal gaji|penghitungan tunjangan|bonus tahunan|kompensasi finansial)\b",
     "Pertanyaan Anda berkaitan dengan penghitungan gaji, tunjangan, atau kompensasi finansial. Sesuai Panduan Operasional NusantaraCare, hal ini berada di luar cakupan operasional internal dan dikelola langsung oleh Bagian SDM / Payroll."),
    (r"\b(evaluasi kinerja|konseling kinerja|penilaian kpi|raport karyawan)\b",
     "Pertanyaan Anda berkaitan dengan evaluasi atau konseling kinerja personal. Layanan ini berada di luar cakupan panduan operasional ini dan dikelola oleh Bagian SDM."),
    (r"\b(resep masakan|siapa presiden|cuaca hari ini|chord gitar|cerpen|puisi)\b",
     "Pertanyaan tidak ditemukan dalam dokumen Panduan Operasional Layanan Internal NusantaraCare v2.0.")
]

class AgentRouter:
    def __init__(self, rag_service: RAGService):
        self.rag_service = rag_service

    def detect_prompt_injection(self, text: str) -> bool:
        lower_text = text.lower()
        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, lower_text, re.IGNORECASE):
                return True
        return False

    def detect_out_of_scope(self, text: str) -> Tuple[bool, str]:
        lower_text = text.lower()
        for pattern, response_msg in OUT_OF_SCOPE_TOPICS:
            if re.search(pattern, lower_text, re.IGNORECASE):
                return True, response_msg
        return False, ""

    async def process_message(self, message: str) -> ChatResponse:
        if not message or not message.strip():
            return ChatResponse(
                answer="Pertanyaan tidak boleh kosong. Silakan ajukan pertanyaan terkait panduan operasional internal NusantaraCare.",
                confidence_label="low",
                reason_code="invalid_input"
            )

        clean_message = message.strip()

        # 1. Guardrail Prompt Injection
        if self.detect_prompt_injection(clean_message):
            return ChatResponse(
                answer="Permintaan tidak dapat diproses karena terdeteksi instruksi yang berpotensi melanggar kebijakan keamanan sistem NusantaraCare.",
                confidence_label="high",
                reason_code="prompt_injection"
            )

        # 2. Guardrail Out-of-Scope (5 area eksplisit tidak tercakup)
        is_oos, oos_response = self.detect_out_of_scope(clean_message)
        if is_oos:
            return ChatResponse(
                answer=f"{oos_response} [Sumber: Dokumen NC-OPS-001, Seksi: Tujuan, Ruang Lingkup, dan Status Dokumen]",
                confidence_label="high",
                reason_code="out_of_scope"
            )

        # 3. Router RAG Pipeline
        return await self.rag_service.answer_query(clean_message)
