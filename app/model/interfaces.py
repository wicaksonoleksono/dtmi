"""
SOLID interfaces for service layer
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple


class IQueryProcessor(ABC):
    """Interface for query processing"""
    @abstractmethod
    async def process_query(
        self,
        query: str,
        top_k: int,
        query_types: Any,
        context_expansion_window: int,
        year: str
    ) -> Dict[str, Any]:
        pass

    """Interface for routing decisions"""
    @abstractmethod
    async def should_use_rag(self, query: str) -> bool:
        pass

    @abstractmethod
    async def analyze_query_context(self, query: str) -> Dict[str, Any]:
        pass


class IContextManager(ABC):
    """Interface for context management"""
    @abstractmethod
    def get_current_contexts(self) -> List[Dict]:
        pass

    @abstractmethod
    def can_elaborate(self) -> bool:
        pass

    @abstractmethod
    def build_conversation_context(self) -> str:
        pass


class IPromptBuilder(ABC):
    """Interface for prompt building"""
    @abstractmethod
    async def build_rag_prompt(
        self,
        query: str,
        retrieved_content: str,
        conversation_context: Optional[str] = None
    ) -> str:
        pass


class IFilterProcessor(ABC):
    """Interface for filter processing - preserves original logic"""
    @abstractmethod
    def get_rag(self, query_types: Any, year: str) -> Tuple[Dict, str]:
        pass
