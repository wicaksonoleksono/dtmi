# app/service/wablass_service.py

import asyncio
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage

from .filter_service import FilterService
from .prompt_service import PromptService
from .chat_history import get_history


class WablassService:
    """Non-streaming service for Wablass WhatsApp integration"""

    def __init__(self, static_dir: str, vectorstore, llm, wablass_agent, router_agent):
        self.static_dir = static_dir
        self.vectorstore = vectorstore
        self.llm = llm
        self.wablass_agent = wablass_agent
        self.router_agent = router_agent

    def get_msg_hist(self, session_id: str) -> List[str]:
        """
        Get conversation context from the last N exchanges (human-AI pairs) for continuation detection
        Returns both human and AI messages in conversation order
        """
        if not session_id:
            return []
        try:
            history = get_history(session_id)
            if not history.messages:
                return []
            # InMemoryHistory already handles MEMORY_EXCHANGES trimming, so just format messages
            conversation_context = []
            for msg in history.messages:
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    if msg.type == 'human':
                        conversation_context.append(f"Human: {msg.content}")
                    elif msg.type == 'ai' or 'ai' in msg.type.lower():
                        conversation_context.append(f"AI: {msg.content}")
            return conversation_context
        except Exception as e:
            print(f"[WABLASS CONTEXT ERROR] Failed to get conversation context: {e}")
            return []

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

        # Initialize services
        router = self.router_agent
        filter_service = FilterService(
            static_dir=self.static_dir,
            vectorstore=self.vectorstore,
            llm=self.llm,
            context_expansion_window=context_expansion_window,
            max_workers=8
        )
        prompt_service = PromptService()

        try:
            # Step 1: Routing decision with conversation context
            previous_conversation = self.get_msg_hist(session_id)
            router_result = await router.get_action(query, previous_conversation)

            # Step 2A: No-RAG path (direct/clarification)
            if router_result['action'] == 'no_rag':
                # Add original query to history before processing
                history = get_history(session_id)
                original_message = HumanMessage(content=query)
                history.add_messages([original_message])
                
                # Build prompt using PromptService
                no_rag_prompt = await prompt_service.build_no_rag_prompt(
                    original_query=query,
                    what_to_clarify=router_result.get('what_to_clarify')
                )
                
                # Process through LLM with session_id
                response = await self.wablass_agent.ainvoke(
                    no_rag_prompt,
                    config={"configurable": {"session_id": session_id}}
                )
                
                clarification_status = "Clarification provided" if router_result.get('what_to_clarify') else "General knowledge"
                return {
                    'answer': response.content,
                    'used_rag': False,
                    'filter_message': clarification_status
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

            # Add original query to history before processing
            history = get_history(session_id)
            original_message = HumanMessage(content=query)
            history.add_messages([original_message])

            response = await self.wablass_agent.ainvoke(
                rag_prompt,
                config={"configurable": {"session_id": session_id}}
            )

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
