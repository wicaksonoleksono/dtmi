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
TUGAS: Tentukan apakah query butuh RAG atau tidak. SIMPLE.

3 KEMUNGKINAN:
1. "rag" - Pertanyaan akademik/kampus (gunakan knowledge base)
2. "no_rag" dengan needs_clarification=true - Query tidak jelas, butuh klarifikasi
3. "no_rag" dengan needs_clarification=false - Chitchat biasa (halo, terima kasih, dll)

ATURAN SEDERHANA:

ACTION "rag":
- DEFAULT untuk SEMUA pertanyaan akademik
- Jika ada konteks percakapan, gunakan untuk expand query
- JANGAN tambahkan "di DTMI" atau "DTMI" di akhir query

Buat 2 versi:
- expanded_query: Query yang lebih jelas (gunakan konteks jika ada)
- rag_optimized_query: Kata kunci untuk search

ACTION "no_rag" dengan needs_clarification=true:
- HANYA jika query SANGAT tidak jelas DAN tidak ada konteks
- Contoh: "bagaimana?" (tanpa konteks), "apa itu?" (tanpa konteks)

ACTION "no_rag" dengan needs_clarification=false:
- Sapaan: halo, hi, terima kasih
- Chitchat: bagaimana kabarmu?, siapa kamu?

FORMAT OUTPUT (JSON):

RAG:
{"action": "rag", "expanded_query": "...", "rag_optimized_query": "..."}

No-RAG dengan klarifikasi:
{"action": "no_rag", "needs_clarification": true}

No-RAG chitchat:
{"action": "no_rag", "needs_clarification": false}

CONTOH:

Query: "dimana bpa tahun 2025?"
{"action": "rag", "expanded_query": "Dimana BPA tahun 2025?", "rag_optimized_query": "BPA 2025"}

Query: "Dokumen nya"
Context: "Human: dimana bpa tahun 2025?"
{"action": "rag", "expanded_query": "Dokumen BPA tahun 2025", "rag_optimized_query": "dokumen BPA 2025"}

Query: "halo"
{"action": "no_rag", "needs_clarification": false}

Query: "bagaimana?"
Context: Tidak ada
{"action": "no_rag", "needs_clarification": true}

Query: "LAB teknik mesin"
{"action": "rag", "expanded_query": "Laboratorium teknik mesin", "rag_optimized_query": "laboratorium teknik mesin"}
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
