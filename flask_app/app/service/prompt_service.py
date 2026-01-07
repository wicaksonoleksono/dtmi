from typing import Optional
from ..model import IPromptBuilder
from ..decorators import handle_service_errors, validate_inputs

class PromptService(IPromptBuilder):
    """
    Single Responsibility: Building prompts for different scenarios
    Domain context is now handled by system prompts in agents
    """

    def __init__(self):
        pass

    @handle_service_errors(service_name="PromptService")
    @validate_inputs(required_params=['query'])
    async def build_rag_prompt(
        self,
        query: str,
        retrieved_content: Optional[str] = None,
    ) -> str:
        # Fallback for empty or None context
        if not retrieved_content or not retrieved_content.strip():
            return f"""Query: ${query}$
Jika data yang diminta tidak ditemukan, jawab:
- "Data tidak dapat ditemukan, namun terdapat informasi yang mungkin relevan."
Jika benar-benar tidak ada, jawab:
- "Data tidak dapat ditemukan. Silakan hubungi administrasi DTMI UGM untuk informasi lebih lanjut."
Jika pertanyaan mengandung link, jawab juga bahwa Anda tidak dapat mengakses internet.
Jika data prosedural atau dokumen tidak ditemukan, Anda boleh mencantumkan referensi kemudian Untuk pertanyaan terkait Dokumen BPA,:
intip.in/softfiledtmi
Untuk pertanyaan yang bersifat general, Anda boleh menjawab,
namun harus memberi disclaimer:
"Jawaban ini berdasarkan informasi umum, bukan data internal DTMI UGM."
Jangan mengarang jawaban dan jangan memberikan informasi yang tidak didukung data.
            """
        
        return f"""
_______________KONTEKS RAG________________________________
Konten: {retrieved_content}
_______________KONTEKS RAG________________________________
Query: ${query}$
"""

    @handle_service_errors(service_name="PromptService")
    @validate_inputs(required_params=['original_query'])
    async def build_no_rag_prompt(
        self,
        original_query: str,
        what_to_clarify: str = None,
    ) -> str:
        # If clarification needed, create clarification prompt
        if what_to_clarify:
            return f"""Pengguna menanyakan: {original_query}
Hal yang perlu di klarifikasi: {what_to_clarify}
Berikan respons klarifikasi yang ramah dan membantu."""
        return original_query

    @handle_service_errors(service_name="PromptService")
    @validate_inputs(required_params=['query'])
    async def build_raw_prompt(
        self,
        query: str,
    ) -> str:
        return f"""Query: {query}"""
