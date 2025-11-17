"""
RouterAgent - Intelligent query routing
Decides whether to use RAG or no-RAG based on query intent
Instructions built internally, receives only LLM and base system prompt from __init__.py
"""

from typing import List, Dict
import json
import re
from langchain_core.messages import SystemMessage, HumanMessage


class RouterAgent:
    """
    RouterAgent with routing instructions built internally
    Receives LLM and base system prompt (DTMI_DOMAIN) from __init__.py
    """

    def __init__(self, llm, system_prompt: str):
        """
        Initialize RouterAgent

        Args:
            llm: LLM instance (configured in __init__.py with nano model)
            system_prompt: Base system prompt (DTMI_DOMAIN from SystemPrompts)
        """
        self.llm = llm
        self.base_system_prompt = system_prompt

        # Build routing instructions internally
        self.routing_instructions = """
TUGAS: Tentukan apakah pertanyaan butuh RAG (pencarian knowledge base) atau tidak.

ATURAN:

ACTION "rag" - Gunakan jika pertanyaan tentang domain akademik/kampus
(informasi spesifik yang membutuhkan data dari knowledge base)
PENTING: Gunakan RAG bahkan jika pertanyaan menggunakan objek umum/general (misal: "berapa bisa diambil?", "kapan deadline?")
Sistem RAG akan mencari dokumen yang relevan berdasarkan konteks.

ACTION "no_rag" - HANYA gunakan untuk:
- Sapaan dan basa-basi (halo, hi, terima kasih)
- Chitchat umum yang tidak ada hubungannya dengan akademik
- Pertanyaan yang BENAR-BENAR tidak bisa dijawab tanpa info esensial yang hilang

KAPAN MINTA KLARIFIKASI:
- HANYA jika pertanyaan benar-benar tidak ada konteks sama sekali dan tidak mungkin dicari
- Contoh butuh klarifikasi: "bagaimana caranya?" (cara apa? tidak ada hint)
- Contoh TIDAK butuh klarifikasi: "berapa bisa diambil?" (bisa dicari dengan keyword "maksimal diambil")

UNTUK ACTION "rag", buat 2 versi query:

1. expanded_query: Pertanyaan yang lebih jelas dengan konteks dari percakapan (jika ada)
   PENTING: JANGAN tambahkan "di DTMI" atau "DTMI" di akhir query
   Contoh: "kalau untuk S2?" → "Apa persyaratan untuk program Magister S2?"
   Contoh: "berapa bisa diambil?" → "Berapa yang bisa diambil?"

2. rag_optimized_query: Kata kunci untuk pencarian (hapus kata tanya, expand singkatan)
   Contoh: "Berapa SKS yang bisa diambil?" → "SKS maksimal diambil"
   Contoh: "matkul apa yang wajib?" → "mata kuliah wajib"
   Contoh: "berapa bisa diambil?" → "maksimal diambil"

FORMAT OUTPUT: JSON
{
  "action": "rag" | "no_rag",
  "expanded_query": "..." (jika rag),
  "rag_optimized_query": "..." (jika rag),
  "what_to_clarify": "..." (jika no_rag dan butuh klarifikasi)
}

CONTOH:
Query: "kalau untuk S2?"
Context: Sebelumnya tanya S1
Output: {"action": "rag", "expanded_query": "Apa persyaratan untuk program Magister S2?", "rag_optimized_query": "persyaratan Magister S2"}

Query: "halo"
Output: {"action": "no_rag"}

Query: "berapa bisa diambil?"
Output: {"action": "rag", "expanded_query": "Berapa yang bisa diambil?", "rag_optimized_query": "maksimal diambil"}

Query: "bagaimana caranya?"
Context: Tidak ada percakapan sebelumnya
Output: {"action": "no_rag", "what_to_clarify": "Cara untuk apa yang dimaksud?"}
"""

        print(f"[ROUTER INIT] RouterAgent initialized with nano LLM")

    async def get_action(self, query: str, previous_conversation: List[str] = None) -> Dict[str, any]:
        """
        Route query to RAG or no-RAG
        System prompt (domain + instructions) automatically prepended

        Args:
            query: User's current query
            previous_conversation: List of previous messages in format ["Human: ...", "AI: ..."]

        Returns:
            RAG Action:
            {
                "action": "rag",
                "expanded_query": str,  # Full proper question for RAG prompt
                "rag_optimized_query": str  # Search terms for vector DB
            }

            No-RAG Action:
            {
                "action": "no_rag",
                "what_to_clarify": str | None  # Present if clarification needed
            }
        """
        previous_conversation = previous_conversation or []

        # Build context from previous conversation
        context_section = ""
        if previous_conversation:
            context_section = f"""
Percakapan Sebelumnya:
{chr(10).join([f"- {msg}" for msg in previous_conversation])}
"""

        # User message - just query + context
        user_message = f"""{context_section}
Query Saat Ini: "{query}"
"""

        # Combine base system prompt + routing instructions
        full_system_prompt = f"{self.base_system_prompt}\n\n{self.routing_instructions}"

        # Build messages with system prompt
        messages = [
            SystemMessage(content=full_system_prompt),
            HumanMessage(content=user_message)
        ]

        # Invoke LLM
        response = await self.llm.ainvoke(messages)
        response_text = response.content if hasattr(response, 'content') else str(response)

        print(f"[ROUTER DEBUG] Response: {response_text[:200]}...")

        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found")

            result = json.loads(json_match.group(0))

            if result.get("action") == "rag":
                return {
                    "action": "rag",
                    "expanded_query": result.get("expanded_query", query),
                    "rag_optimized_query": result.get("rag_optimized_query", query)
                }
            else:  # no_rag action
                return {
                    "action": "no_rag",
                    "what_to_clarify": result.get("what_to_clarify", None)
                }

        except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
            print(f"[ROUTER ERROR] Failed to parse router response: {e}")
            print(f"[ROUTER ERROR] Raw response: {response_text}")
            # Robust fallback - always use RAG with original query
            return {
                "action": "rag",
                "expanded_query": query,
                "rag_optimized_query": query
            }
