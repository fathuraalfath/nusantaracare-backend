import os
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import chromadb
from app.schemas import ChatResponse

load_dotenv()

# Konfigurasi NotispaceAI / OpenAI
NOTISPACE_API_KEY = os.getenv("NOTISPACE_API_KEY", "")
NOTISPACE_BASE_URL = os.getenv("NOTISPACE_BASE_URL", "https://api.notispace.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", NOTISPACE_API_KEY)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", NOTISPACE_BASE_URL if NOTISPACE_API_KEY else None)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma_db")

DOC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "raw_docs", "nusantaracare_panduan_operasional_internal_v2.md")

class RAGService:
    def __init__(self):
        # Inisialisasi ChromaDB client
        os.makedirs(CHROMA_PERSIST_DIRECTORY, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIRECTORY)
        self.collection_name = "nusantaracare_knowledge_base"
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "NusantaraCare Operational Manual v2.0 with v1.4 archive"}
        )
        # Indeks dokumen jika koleksi masih kosong
        if self.collection.count() == 0:
            self._index_document()

    def _parse_markdown_document(self) -> List[Dict[str, Any]]:
        """
        Membaca dan mem-parsing dokumen markdown nusantaracare v2.0 menjadi chunk berbasis seksi struktural.
        Metadata: doc_id, doc_title, doc_version, is_active, section_title, effective_date
        """
        if not os.path.exists(DOC_PATH):
            raise FileNotFoundError(f"Dokumen sumber tidak ditemukan di {DOC_PATH}")

        with open(DOC_PATH, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Ekstrak metadata frontmatter
        doc_id = "NC-OPS-001"
        doc_title = "Panduan Operasional Layanan Internal NusantaraCare"
        doc_version_default = "2.0"
        effective_date_default = "2026-07-01"

        fm_match = re.search(r"^---\s*\n(.*?)\n---\s*\n", raw_text, re.DOTALL)
        content_text = raw_text
        if fm_match:
            fm_text = fm_match.group(1)
            content_text = raw_text[fm_match.end():]
            for line in fm_text.splitlines():
                if line.startswith("doc_id:"):
                    doc_id = line.split(":", 1)[1].strip()
                elif line.startswith("doc_title:"):
                    doc_title = line.split(":", 1)[1].strip()
                elif line.startswith("doc_version:"):
                    doc_version_default = line.split(":", 1)[1].strip().replace('"', '')
                elif line.startswith("effective_date:"):
                    effective_date_default = line.split(":", 1)[1].strip().replace('"', '')

        chunks = []
        # Pecah berdasarkan heading level 2 (##)
        sections = re.split(r'\n(?=##\s+)', content_text)
        chunk_idx = 1

        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue

            # Ambil judul H2
            h2_match = re.match(r'^##\s+(.+)', sec)
            h2_title = h2_match.group(1).strip() if h2_match else "Umum"

            # Pecah lagi berdasarkan subseksi H3 (###) jika ada
            subsections = re.split(r'\n(?=###\s+)', sec)
            if len(subsections) > 1:
                # Ada subseksi
                intro_part = subsections[0].strip()
                if intro_part and not intro_part.startswith("##"):
                    intro_part = f"## {h2_title}\n\n" + intro_part

                if intro_part:
                    chunks.append(self._create_chunk_dict(
                        doc_id=doc_id,
                        doc_title=doc_title,
                        section_title=h2_title,
                        content=intro_part,
                        chunk_id=f"{doc_id}_c{chunk_idx:03d}",
                        doc_version=doc_version_default,
                        effective_date=effective_date_default,
                        is_active=True
                    ))
                    chunk_idx += 1

                for sub in subsections[1:]:
                    sub = sub.strip()
                    if not sub:
                        continue
                    h3_match = re.match(r'^###\s+(.+)', sub)
                    h3_title = h3_match.group(1).strip() if h3_match else ""
                    combined_section = f"{h2_title} > {h3_title}"

                    # Cek apakah ini arsip v1.4 yang nonaktif
                    is_v14_archive = "1.4" in h3_title or "NONAKTIF" in h3_title or "v1.4" in sub
                    chunk_version = "1.4" if is_v14_archive else "2.0"
                    is_active = False if is_v14_archive else True
                    eff_date = "2025-01-01" if is_v14_archive else effective_date_default

                    chunks.append(self._create_chunk_dict(
                        doc_id=doc_id,
                        doc_title=doc_title,
                        section_title=combined_section,
                        content=sub,
                        chunk_id=f"{doc_id}_c{chunk_idx:03d}",
                        doc_version=chunk_version,
                        effective_date=eff_date,
                        is_active=is_active
                    ))
                    chunk_idx += 1
            else:
                # Tidak ada H3, gunakan seluruh seksi
                is_v14_archive = "1.4" in h2_title or "NONAKTIF" in h2_title
                chunk_version = "1.4" if is_v14_archive else "2.0"
                is_active = False if is_v14_archive else True
                eff_date = "2025-01-01" if is_v14_archive else effective_date_default

                chunks.append(self._create_chunk_dict(
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section_title=h2_title,
                    content=sec,
                    chunk_id=f"{doc_id}_c{chunk_idx:03d}",
                    doc_version=chunk_version,
                    effective_date=eff_date,
                    is_active=is_active
                ))
                chunk_idx += 1

        return chunks

    def _create_chunk_dict(self, doc_id: str, doc_title: str, section_title: str,
                           content: str, chunk_id: str, doc_version: str,
                           effective_date: str, is_active: bool) -> Dict[str, Any]:
        return {
            "chunk_id": chunk_id,
            "content": content,
            "metadata": {
                "doc_id": doc_id,
                "doc_title": doc_title,
                "section_title": section_title,
                "doc_version": doc_version,
                "effective_date": effective_date,
                "is_active": str(is_active)  # Chroma metadata supports primitive types
            }
        }

    def _index_document(self):
        chunks = self._parse_markdown_document()
        if not chunks:
            return

        ids = [c["chunk_id"] for c in chunks]
        documents = [f"Dokumen: {c['metadata']['doc_title']} (v{c['metadata']['doc_version']})\nSeksi: {c['metadata']['section_title']}\nStatus Aktif: {c['metadata']['is_active']}\n\n{c['content']}" for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

    def retrieve(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """
        Melakukan retrieval chunk teratas dari ChromaDB berdasarkan kemiripan teks pertanyaan.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        retrieved_chunks = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0] if "distances" in results else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, dists):
                retrieved_chunks.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": dist
                })

        return retrieved_chunks

    async def answer_query(self, query: str) -> ChatResponse:
        retrieved = self.retrieve(query, top_k=4)

        if not retrieved:
            return ChatResponse(
                answer="Informasi tidak ditemukan dalam dokumen Panduan Operasional Layanan Internal NusantaraCare v2.0.",
                confidence_label="low",
                reason_code="no_relevant_context"
            )

        # Cek threshold jarak vector jika model Chroma default
        best_distance = retrieved[0]["distance"] if "distance" in retrieved[0] else 0.0

        # Susun konteks untuk LLM
        context_parts = []
        sources = []
        has_active_context = False

        for item in retrieved:
            meta = item["metadata"]
            sec = meta.get("section_title", "Umum")
            ver = meta.get("doc_version", "2.0")
            is_act = meta.get("is_active", "True") == "True"
            if is_act:
                has_active_context = True

            source_label = f"Doc: {meta.get('doc_id', 'NC-OPS-001')}, Seksi: {sec} (v{ver}, Status: {'Aktif' if is_act else 'NONAKTIF'})"
            if source_label not in sources:
                sources.append(source_label)

            context_parts.append(
                f"--- SUMBER KONTEKS: {source_label} ---\n{item['content']}\n"
            )

        context_str = "\n".join(context_parts)

        # System prompt RAG ketat
        system_prompt = (
            "Anda adalah Asisten AI Resmi untuk Panduan Operasional Layanan Internal NusantaraCare.\n"
            "TUGAS UTAMA:\n"
            "Jawab pertanyaan karyawan HANYA berdasarkan konteks dokumen internal NusantaraCare yang disediakan di bawah.\n"
            "ATURAN MUTLAK:\n"
            "1. JANGAN PERNAH mengarang, berasumsi, atau mengekstrapolasi di luar konteks yang diberikan.\n"
            "2. Jika jawaban tidak ditemukan secara jelas di dalam konteks, jawab persis: 'Informasi tidak ditemukan dalam dokumen Panduan Operasional Layanan Internal NusantaraCare v2.0.'\n"
            "3. ATURAN VERSI PENTING (v1.4 vs v2.0):\n"
            "   - Ketentuan versi 1.4 sudah NONAKTIF sejak 1 Juli 2026 dan TIDAK BERLAKU LAGI untuk keputusan operasional.\n"
            "   - Versi 2.0 adalah satu-satunya acuan operasional yang AKTIF.\n"
            "   - Jika pemohon bertanya aturan operasional umum/saat ini, SELALU gunakan ketentuan v2.0.\n"
            "   - Jika pemohon bertanya riwayat atau perbedaan v1.4, jelaskan bahwa ketentuan v1.4 sudah nonaktif sejak 1 Juli 2026 dan sebutkan penggantinya di v2.0.\n"
            "4. KUTIPAN SUMBER: Di akhir setiap jawaban, WAJIB sertakan kutipan sumber spesifik dalam format: [Sumber: Dokumen NC-OPS-001, Seksi: <Nama Seksi> (v<Versi>)].\n"
        )

        user_content = f"KONTEKS DOKUMEN:\n{context_str}\n\nPERTANYAAN KARYAWAN:\n{query}"

        # Periksa apakah API key Notispace / OpenAI tersedia
        api_key = os.getenv("NOTISPACE_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("NOTISPACE_BASE_URL") or os.getenv("OPENAI_BASE_URL")

        if api_key and api_key.strip() and not api_key.startswith("your_"):
            try:
                from openai import AsyncOpenAI
                client_kwargs = {"api_key": api_key.strip()}
                if base_url and base_url.strip():
                    client_kwargs["base_url"] = base_url.strip()

                client = AsyncOpenAI(**client_kwargs)

                completion = await client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.0
                )
                answer_text = completion.choices[0].message.content.strip()

                # Tentukan confidence dan reason_code berdasarkan respons
                if "tidak ditemukan dalam dokumen" in answer_text.lower():
                    return ChatResponse(
                        answer=answer_text,
                        confidence_label="low",
                        reason_code="no_relevant_context"
                    )

                confidence = "high" if best_distance < 1.0 else "medium"
                return ChatResponse(
                    answer=answer_text,
                    confidence_label=confidence,
                    reason_code="answered"
                )
            except Exception as e:
                # Log error and fallback
                pass

        # Fallback jika API key belum diset atau offline
        # ponytail: deterministic rule/context extraction fallback if LLM API is unavailable
        return self._generate_extractive_fallback(query, retrieved, sources)

    def _generate_extractive_fallback(self, query: str, retrieved: List[Dict[str, Any]], sources: List[str]) -> ChatResponse:
        """Fallback cerdas berbasis ekstraksi konteks langsung ketika LLM API offline."""
        if not retrieved:
            return ChatResponse(
                answer="Informasi tidak ditemukan dalam dokumen Panduan Operasional Layanan Internal NusantaraCare v2.0.",
                confidence_label="low",
                reason_code="no_relevant_context"
            )

        top_chunk = retrieved[0]
        dist = top_chunk.get("distance", 0.0)

        # Threshold jarak vektor Chroma: jika > 1.15, anggap tidak relevan
        if dist > 1.15:
            return ChatResponse(
                answer="Informasi tidak ditemukan dalam dokumen Panduan Operasional Layanan Internal NusantaraCare v2.0.",
                confidence_label="low",
                reason_code="no_relevant_context"
            )

        meta = top_chunk["metadata"]
        sec_title = meta.get("section_title", "Umum")
        ver = meta.get("doc_version", "2.0")
        text = top_chunk["content"]

        # Verifikasi leksikal sederhana untuk fallback offline:
        # Periksa rasio kata kunci bermakna yang muncul di chunk teratas
        stop_words = {"apakah", "bagaimana", "kapan", "siapa", "mengapa", "dimana", "berapa", "untuk", "dalam", "dengan", "pada", "dari", "yang", "atau", "adalah", "kantor", "nusantaracare", "layanan", "internal", "bisa", "dapat", "saya", "kami", "anda"}
        q_words = [w for w in re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', query.lower()) if w not in stop_words]
        chunk_lower = text.lower()

        # Jika query memiliki kata kunci spesifik tetapi rasio kecocokan di chunk rendah (< 40%)
        if q_words:
            matched_words = [w for w in q_words if w in chunk_lower]
            match_ratio = len(matched_words) / len(q_words)
            if match_ratio < 0.40:
                return ChatResponse(
                    answer="Informasi tidak ditemukan dalam dokumen Panduan Operasional Layanan Internal NusantaraCare v2.0.",
                    confidence_label="low",
                    reason_code="no_relevant_context"
                )

        # Ekstrak paragraf/jawaban terbaik dari chunk
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("Dokumen:") and not l.startswith("Seksi:") and not l.startswith("Status")]
        
        # Jika chunk berupa FAQ (memiliki pola **T: ... dan J: ...)
        faq_pairs = []
        current_q = ""
        for line in lines:
            if line.startswith("**T:") or line.startswith("T:"):
                current_q = line.replace("**", "").replace("T:", "").strip()
            elif line.startswith("J:") and current_q:
                ans = line[2:].strip()
                faq_pairs.append((current_q, ans))
                current_q = ""

        if faq_pairs:
            # Cari pasangan FAQ yang pertanyaannya paling cocok dengan kata kunci query
            best_pair_ans = None
            max_common = -1
            for q_text, a_text in faq_pairs:
                common_count = sum(1 for w in q_words if w in q_text.lower() or w in a_text.lower())
                if common_count > max_common:
                    max_common = common_count
                    best_pair_ans = a_text

            body = best_pair_ans if best_pair_ans else faq_pairs[0][1]
        else:
            # Bukan FAQ, ambil paragraf teks SOP
            content_lines = [l for l in lines if not l.startswith("#") and not l.startswith("|")]
            body = " ".join(content_lines[:3])

        answer_str = f"{body} [Sumber: Dokumen NC-OPS-001, Seksi: {sec_title} (v{ver})]"
        return ChatResponse(
            answer=answer_str,
            confidence_label="high" if dist < 0.8 else "medium",
            reason_code="answered"
        )
