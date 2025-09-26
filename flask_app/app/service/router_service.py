from typing import List, Dict
import json


class RouterAgent:
    def __init__(self, llm, dtmi_domain: str):
        self.llm = llm
        self.dtmi_domain = dtmi_domain

    async def get_action(self, query: str, previous_conversation: List[str]) -> Dict[str, any]:
        """
        Unified RouterAgent with context-aware decision making:
        1. Continuation detection + query expansion from conversation history
        2. Single decision: RAG needed or not?

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
            "response": str,  # Direct response content
            "what_to_clarify": str | None  # Present if clarification needed
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
Kamu adalah RouterAgent dengan 2 aksi sederhana:
Domain: 
{self.dtmi_domain}

{context_section}
Query Saat Ini: "{query}"

TUGAS:
1. CONTEXT ANALYSIS: Analisis percakapan untuk memahami intent lengkap
2. DECISION: Apakah butuh pencarian knowledge base (RAG) atau tidak?

ATURAN KEPUTUSAN:
- ACTION "rag": Butuh informasi spesifik DTMI (mata kuliah, dosen, kurikulum, persyaratan, dll)
- ACTION "no_rag": Untuk sapaan, chitchat, clarification, atau general response

KAPAN BUTUH CLARIFICATION (gunakan no_rag + what_to_clarify):
- Istilah ambigu: "matkul" → clarify SKS vs mata kuliah, "program" → clarify S1/S2/S3
- Pronoun tidak jelas: "itu", "yang lain" tanpa referent
- Konteks hilang: "berapa bisa diambil?" tanpa subjek
- Pertanyaan tidak lengkap: "bagaimana?" tanpa objek yang jelas
- Angka tanpa konteks: "14 SKS bagaimana?" → apa aspek yang ditanyakan?
- Skenario samar: "kalau misal..." tanpa pertanyaan spesifik
- Nama tanpa klarifikasi: "Siapa ari" -> apakah yang dimaksud ari dosen atau siapa ?

RAG_OPTIMIZED_QUERY RULES (untuk rag action):
- HAPUS semua kata tanya: berapa, siapa, kapan, dimana, bagaimana, apa, gimana
- HAPUS stop words: yang, adalah, untuk, dengan, dari, ke, di, dalam, bisa, dapat
- PERTAHANKAN kata kunci penting: SKS, IPK, mata kuliah, dosen, persyaratan, dll
- Contoh: "Berapa SKS yang bisa diambil?" → "SKS diambil", "Siapa dosen TI?" → "dosen TI"

SINGKATAN:
TI → Teknik Industri, TM → Teknik Mesin, matkul → mata kuliah (clarify SKS?), prof → professor, tendik → tenaga pendidikan

CONTOH:
Input: "kalau untuk S2?" (setelah "Apa persyaratan S1?")
Output: {{
  "action": "rag",
  "expanded_query": "Apa persyaratan untuk program S2 Teknik Mesin?",
  "rag_optimized_query": "persyaratan program S2 Teknik Mesin"
}}

Input: "Halo, apa kabar?"
Output: {{
  "action": "no_rag",
  "response": "Halo! Saya Tasya, asisten DTMI UGM. Apa yang bisa saya bantu?"
}}

Input: "kalo sy punya ipk 2.5 matkul yang sy bs ambil brapa?"
Output: {{
  "action": "no_rag",
  "response": "Apakah yang dimaksud adalah SKS (Sistem Kredit Semester) yang bisa diambil dengan IPK 2.5?",
  "what_to_clarify": "user_intent"
}}

Input: "kalau misal saya mengambil 14 SKS bagaimana?"
Output: {{
  "action": "no_rag",
  "response": "Untuk 14 SKS, apa yang ingin Anda ketahui? Apakah tentang minimum IPK yang diperlukan, dampak terhadap beban studi, atau aspek lainnya?",
  "what_to_clarify": "specific_aspect"
}}

** STRICT RULES **
- JANGAN tambah kata kunci di luar pertanyaan untuk expanded_query dan rag_optimized_query
- JANGAN tambah suffix "DTMI UGM" karena mengacaukan RAG
- PERTAHANKAN kata tanya Bahasa Indonesia dalam rag_optimized_query
- Meskipun konteks sebelumnya pernah ditanyakan, tetap gunakan RAG jika butuh knowledge base

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

            if result.get("action") == "rag":
                return {
                    "action": "rag",
                    "expanded_query": result.get("expanded_query", query),
                    "rag_optimized_query": result.get("rag_optimized_query", query)
                }
            else:  # no_rag action
                return {
                    "action": "no_rag",
                    "response": result.get("response", query),
                    "what_to_clarify": result.get("what_to_clarify", None)
                }

        except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
            print(f"[ROUTER ERROR] Failed to parse router response: {e}")
            print(f"[ROUTER ERROR] Raw response: {response_text}")
            # Robust fallback - always use RAG with original query
            return {
                "action": "rag",  # Safe fallback to RAG
                "expanded_query": query,
                "rag_optimized_query": query
            }
