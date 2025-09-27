# app/service/wablass_service.py

import asyncio
from typing import Dict, Any
from langchain_core.messages import HumanMessage

from .filter_service import FilterService
from .router_service import RouterAgent
from .prompt_service import PromptService


class WablassService:
    """Non-streaming service for Wablass WhatsApp integration"""

    def __init__(self, static_dir: str, vectorstore, llm, wablass_agent):
        self.static_dir = static_dir
        self.vectorstore = vectorstore
        self.llm = llm
        self.wablass_agent = wablass_agent

    async def generate_answer(
        self,
        query: str,
        query_types: str = "all",
        year: str = "all",
        top_k: int = 8,
        context_expansion_window: int = 3,
        session_id: str = "wablass_session"
    ) -> Dict[str, Any]:
        """Generate answer using the same pipeline as stream_query but non-streaming"""

        DTMI_DOMAIN = """
        Domain mencakup:
        - Detail mata kuliah (nama, kode, SKS, prasyarat)
        - Peminatan mata kuliah
        - Capaian pembelajaran spesifik
        - Jadwal perkuliahan dan ujian tertentu
        - Prosedur akademik dan administrasi resmi
        - Data dosen dan staff (nama, jabatan, kepakaran)
        - Data dosen jika terdengar seperti nama indonesia maka gunakan rag
        - Struktur kurikulum dan silabus detail
        - Persyaratan kelulusan program studi
        - Program beasiswa spesifik DTMI
        - Fasilitas kampus DTMI
        - Kegiatan akademik DTMI
        - Data umum yang berkaitan dengan jogjakarta dan UGM
        """

        # Initialize services
        router = RouterAgent(self.llm, DTMI_DOMAIN)
        filter_service = FilterService(
            static_dir=self.static_dir,
            vectorstore=self.vectorstore,
            llm=self.llm,
            context_expansion_window=context_expansion_window,
            max_workers=8
        )
        prompt_service = PromptService(DTMI_DOMAIN)

        try:
            # Step 1: Routing decision (no previous messages for WhatsApp)
            router_result = await router.get_action(query, [])

            # Step 2A: No-RAG path (direct/clarification)
            if router_result['action'] == 'no_rag':
                if router_result.get('what_to_clarify'):
                    # Clarification case - return directly without LLM processing
                    return {
                        'answer': router_result['response'],
                        'used_rag': False,
                        'context': '',
                        'filter_message': f'Clarification needed: {router_result["what_to_clarify"]}',
                        'sources': []
                    }
                else:
                    # Direct response case - process through LLM
                    response = await self.wablass_agent.ainvoke([HumanMessage(content=router_result['response'])])
                    return {
                        'answer': response.content,
                        'used_rag': False,
                        'filter_message': 'Direct response (no RAG)'
                    }

            # Step 2B: RAG path
            rag_result = await filter_service.get_rag(
                query=router_result['rag_optimized_query'],  # Use optimized keywords for search
                query_types=query_types,
                year=year,
                top_k=top_k,
                context_expansion_window=context_expansion_window,
                relevance_query=router_result['expanded_query']  # Use full question for relevance
            )

            rag_prompt = await prompt_service.build_rag_prompt(
                query=router_result['expanded_query'],  # Use full question for prompt
                retrieved_content=rag_result['context']
            )

            response = await self.wablass_agent.ainvoke([HumanMessage(content=rag_prompt)])

            return {
                'answer': response.content,
                'used_rag': True,
                'filter_message': rag_result.get('filter_message', ''),
                'context_used': rag_result['context'][:200] + "..." if rag_result['context'] else ""
            }

        except Exception as e:
            # Fallback response
            return {
                'answer': f"Maaf, terjadi kesalahan dalam memproses pertanyaan Anda: {str(e)}",
                'used_rag': False,
                'filter_message': 'Error occurred',
                'error': str(e)
            }
