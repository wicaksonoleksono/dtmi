"""
SOLID Prompt Service - Single Responsibility for Prompt Building
"""

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
        
        # For general knowledge, just return original query
        return original_query

    @handle_service_errors(service_name="PromptService")
    @validate_inputs(required_params=['query'])
    async def build_raw_prompt(
        self,
        query: str,
    ) -> str:
        return f"""Query: {query}"""
