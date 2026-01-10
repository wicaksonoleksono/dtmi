# app/model/rag.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from .enums import Filter, Year  # reuse existing enums


@dataclass(frozen=True)
class DocMeta:
    id: str
    type: str
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    chunk_index: Optional[int] = None
    total_chunks_in_section: Optional[int] = None
    score: float = 0.0
    caption: Optional[str] = None
    csv_path: Optional[str] = None
    image_path: Optional[str] = None
    row_data: Optional[Dict[str, Any]] = None
    year: Optional[str] = None
    dep: Optional[str] = None  # "tm" / "ti" / missing


@dataclass(frozen=True)
class RagHit:
    content: str
    meta: DocMeta


@dataclass(frozen=True)
class RagContext:
    context: str
    image_paths: List[Tuple[str, str]]
    csv_paths: List[Tuple[str, str]]
    metadatas: List[Dict[str, Any]]
    csv_content: Dict[str, str]
    query_type_used: Union[str, List[str]]
    filter_message: str


class IFilterProcessor(ABC):
    """Public contract. No dict voodoo. Checkboxy inputs."""
    @abstractmethod
    async def get_rag(
        self,
        query: str,
        query_types: Union[str, List[str]] = "all",  # "image" | "table" | "text" or ["image","table"]
        year: Optional[str] = None,                  # "2024", "2025", etc.
        dep: Optional[str] = None,                   # "tm" | "ti" | None
        top_k: int = 20,
        context_expansion_window: Optional[int] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError
