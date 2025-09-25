"""
Deterministic response models for consistent JSON output
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
import json


@dataclass
class FilterInfo:
    """Filter information for debugging"""
    query_types: Optional[Any]
    year: str
    filter_applied: str
    tendik_included: bool = True
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ProcessingStats:
    """Processing statistics"""
    total_time: float
    search_time: Optional[float] = None
    processing_time: Optional[float] = None
    relevance_time: Optional[float] = None
    context_expansion_used: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass 
class ContextInfo:
    """Context information"""
    conversation_context: str
    context_used: bool
    enhanced_query: Optional[str] = None
    original_query: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RAGResult:
    """RAG processing result"""
    answer: str
    metadatas: List[Dict]
    csv_paths: List[tuple]
    image_paths: List[tuple] 
    use_rag: bool
    context_info: ContextInfo
    processing_stats: Optional[ProcessingStats] = None
    filter_info: Optional[FilterInfo] = None
    
    def to_dict(self) -> Dict:
        return {
            "answer": self.answer,
            "metadatas": self.metadatas,
            "csv_paths": self.csv_paths,
            "image_paths": self.image_paths,
            "use_rag": self.use_rag,
            "context_info": self.context_info.to_dict(),
            "processing_stats": self.processing_stats.to_dict() if self.processing_stats else None,
            "filter_info": self.filter_info.to_dict() if self.filter_info else None
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class SimpleResponse:
    """Simple response for non-RAG queries"""
    answer: str
    context_info: ContextInfo
    processing_stats: Optional[ProcessingStats] = None
    
    def to_dict(self) -> Dict:
        return {
            "answer": self.answer,
            "metadatas": [],
            "csv_paths": [],
            "image_paths": [],
            "use_rag": False,
            "context_info": self.context_info.to_dict(),
            "processing_stats": self.processing_stats.to_dict() if self.processing_stats else None
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)