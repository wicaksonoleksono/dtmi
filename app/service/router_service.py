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
Klasifikasi query ke salah satu dari 3 aksi. Output HANYA JSON, tanpa penjelasan.

AKSI:
1. "rag" — Pertanyaan akademik/kampus/dosen/apapun yang butuh knowledge base (DEFAULT).
2. "clarify" — Query SANGAT ambigu DAN TANPA konteks percakapan. Sertakan what_to_clarify.
3. "chitchat" — Sapaan/basa-basi (halo, terima kasih, siapa kamu, bagaimana kabarmu, dll).

ATURAN untuk "rag":
- Gunakan konteks percakapan sebelumnya untuk memperjelas query.
- JANGAN tambahkan "DTMI" di query.
- expanded_query = kalimat lengkap, rag_optimized_query = kata kunci search saja.
- WAJIB ganti SEMUA singkatan di expanded_query DAN rag_optimized_query dengan bentuk panjangnya.
  Gunakan daftar "Singkatan" dari system prompt di atas. Case-insensitive (kaprodi = KAPRODI).
  Singkatan TIDAK BOLEH muncul di output. Ganti semua.

FORMAT OUTPUT:
{"action": "rag", "expanded_query": "...", "rag_optimized_query": "..."}
{"action": "clarify", "what_to_clarify": "jelaskan apa yang ambigu"}
{"action": "chitchat"}
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

        print(f"[ROUTER] Query: \"{query}\"")
        print(f"[ROUTER] Context: {previous_conversation if previous_conversation else 'None'}")
        print(f"[ROUTER] User message sent to LLM:\n{user_message.strip()}")

        # Build messages with system prompt
        messages = [
            SystemMessage(content=full_system_prompt),
            HumanMessage(content=user_message)
        ]

        # Invoke LLM
        response = await self.llm.ainvoke(messages)
        response_text = response.content if hasattr(response, 'content') else str(response)

        print(f"[ROUTER] Raw LLM response: {response_text}")

        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found")

            result = json.loads(json_match.group(0))
            action = result.get("action", "")
            print(f"[ROUTER] Parsed JSON: {result}")

            if action == "rag":
                out = {
                    "action": "rag",
                    "expanded_query": result.get("expanded_query", query),
                    "rag_optimized_query": result.get("rag_optimized_query", query)
                }
                print(f"[ROUTER] → RAG | expanded: \"{out['expanded_query']}\" | search: \"{out['rag_optimized_query']}\"")
                return out
            elif action == "clarify":
                out = {
                    "action": "no_rag",
                    "what_to_clarify": result.get("what_to_clarify", "Bisa diperjelas pertanyaannya?")
                }
                print(f"[ROUTER] → CLARIFY | what_to_clarify: \"{out['what_to_clarify']}\"")
                return out
            elif action == "chitchat":
                out = {
                    "action": "no_rag",
                    "what_to_clarify": None
                }
                print(f"[ROUTER] → CHITCHAT")
                return out
            else:
                raise ValueError(f"Unknown action: '{action}'")

        except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
            print(f"[ROUTER ERROR] Failed to parse router response: {e}")
            print(f"[ROUTER ERROR] Raw response: {response_text}")
            # Robust fallback - always use RAG with original query
            print(f"[ROUTER] → FALLBACK to RAG with original query: \"{query}\"")
            return {
                "action": "rag",
                "expanded_query": query,
                "rag_optimized_query": query
            }
