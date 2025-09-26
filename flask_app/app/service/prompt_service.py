"""
SOLID Prompt Service - Single Responsibility for Prompt Building
"""

from typing import Optional
from ..model import IPromptBuilder
from ..decorators import handle_service_errors, validate_inputs


class PromptService(IPromptBuilder):
    """
    Single Responsibility: Building prompts for different scenarios
    """

    def __init__(self, domain_context: str):
        self.domain_context = domain_context

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

PENTING: Tidak ada konteks yang relevan ditemukan dengan kueri. Jawab dengan:
Jika dapat dijawab dengan general knowledge maka Bisa jawab secara general
"Mohon maaf, data tidak ditemukan. Silakan hubungi administrasi DTMI UGM 🙏"
"""
        
        return f"""
_______________KONTEKS RAG________________________________
Konten: {retrieved_content}
_______________KONTEKS RAG________________________________
Query: ${query}$
"""

    @handle_service_errors(service_name="PromptService")
    @validate_inputs(required_params=['response'])
    async def build_no_rag_prompt(
        self,
        response: str,
        what_to_clarify: str = None,
    ) -> str:
        # If clarification needed, wrap with $$ so LLM knows it's asking clarification
        if what_to_clarify:
            return f"""Query: ${response}$
Ini adalah permintaan klarifikasi untuk membantu user memperjelas maksud mereka.
apa yang perlu di klarifikasi: {what_to_clarify if what_to_clarify else "tidak ada yang perlu diklarifikasi"}
Berikan respons klarifikasi yang ramah dan membantu sesuai yang diminta.
jika tidak terdapat klarifikasi maka dapat langsung dijawab
"""
        
        # For direct responses, return without $$ wrapper (stored as-is in history)
        return response

    @handle_service_errors(service_name="PromptService")
    @validate_inputs(required_params=['query'])
    async def build_raw_prompt(
        self,
        query: str,
    ) -> str:
        return f"""Query: {query}"""
