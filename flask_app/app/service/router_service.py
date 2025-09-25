from typing import List, Dict
import json


class RouterAgent:
    def __init__(self, llm, dtmi_domain: str):
        self.llm = llm
        self.dtmi_domain = dtmi_domain

    async def get_action(self, query: str, previous_conversation: List[str]) -> Dict[str, any]:
        """
        Enhanced RouterAgent with dual-purpose logic:
        1. Continuation detection + query expansion
        2. RAG decision + query optimization

        Returns:
        {
            "action": str,  # "rag" | "direct" | "clarify"
            "expanded_query": str,  # Full proper question
            "rag_optimized_query": str | None,  # Search terms for vector DB (null for clarify)
            "clarification_needed": str | None  # Clarification question (only for clarify)
        }
        """
        # Build context from previous conversation (human-AI pairs)
        context_section = ""
        if previous_conversation:
            context_section = f"""
Percakapan Sebelumnya:
{chr(10).join([f"- {msg}" for msg in previous_conversation])}
"""

        router_prompt = f"""
Kamu adalah RouterAgent yang menangani 4 tugas sekaligus:
Domain: 
{self.dtmi_domain}

{context_section}
Query Saat Ini: "{query}"

TUGAS:
1. CONTINUATION DETECTION: Apakah query saat ini kelanjutan dari pesan sebelumnya?
2. QUERY EXPANSION: Jika kelanjutan, bentuk menjadi pertanyaan lengkap yang standalone
3. ACTION DECISION: Tentukan tindakan yang tepat
4. OPTIMIZATION: Generate kata kunci optimal untuk vector search (jika RAG)

ATURAN ACTION DECISION:
- ACTION "rag": Informasi spesifik DTMI (mata kuliah, dosen, kurikulum, dll)
- ACTION "direct": Chitchat, sapaan, pertanyaan filosofis umum, definisi DTMI, siapa Anda, perbedaan TI dan TM
- ACTION "clarify": Query ambigu, istilah tidak jelas, konteks tidak cukup

CLARIFICATION TRIGGERS:
- Istilah ambigu: "matkul" vs "sks", "program" tanpa spesifikasi
- Pronoun tidak jelas: "itu", "yang lain", "departemen itu"
- Konteks tidak cukup dari 3 pesan terakhir
- Multiple interpretations possible

CONTOH:
Input: "kalau untuk S2?" (setelah "Apa persyaratan S1?")
Output: {{
  "action": "rag",
  "expanded_query": "Apa persyaratan untuk program S2 Teknik Mesin?",
  "rag_optimized_query": "persyaratan program S2 Teknik Mesin",
  "clarification_needed": null
}}

Input: "Halo, apa kabar?"
Output: {{
  "action": "direct",
  "expanded_query": "Halo, apa kabar?",
  "rag_optimized_query": null,
  "clarification_needed": null
}}

Input: "kalo sy punya ipk 2.5 matkul yang sy bs ambil brapa?"
Output: {{
  "action": "clarify",
  "expanded_query": "Kalau Saya memiliki ipk 2.5 berapa SKS yang bisa saya ambil sebgai matkul",
  "rag_optimized_query": null,
  "clarification_needed": "Apakah yang dimaksud adalah SKS (Sistem Kredit Semester) yang bisa diambil dengan IPK 2.5?"
}}
** STRICT **
JANGAN MENAMBAH KATAKUNCI DULUAR PERTANYAAN UNTUK EXPENDED QUERY DAN UNTUK RAG_OPTIMIZED_QUERY
. HANYA MEMBENARKAN KALIMAT SAJA. KARENA AKAN MENGACAUKAN HASIL
JANGAN MENAMBAHKAN SUFFIX DTMI UGM. KARENA AKAN MENGACAUKAN RAG 

Meskipun Konteks sebelumnya pernah ditanyakan tolong tetap gunakan RAG


FORMAT RESPONSE: JSON ketat  

"""

        response = await self.llm.ainvoke(router_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)

        try:
            # Extract JSON from response
            import re
            import json
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found")

            result = json.loads(json_match.group(0))

            return {
                "action": result.get("action", "rag"),  # Safer to default to RAG
                "expanded_query": result.get("expanded_query", query),
                "rag_optimized_query": result.get("rag_optimized_query", query),
                "clarification_needed": result.get("clarification_needed", None)
            }

        except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
            print(f"[ROUTER ERROR] Failed to parse router response: {e}")
            print(f"[ROUTER ERROR] Raw response: {response_text}")
            # Robust fallback - always use RAG with original query
            return {
                "action": "rag",  # Safe fallback to RAG
                "expanded_query": query,
                "rag_optimized_query": query,
                "clarification_needed": None
            }
