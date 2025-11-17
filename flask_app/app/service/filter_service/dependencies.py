# app/service/filter_service/dependencies.py

from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass
class FilterServiceDeps:
    """
    Shared state container for FilterService modules
    Maintains caches, thread pool, and mutable configuration
    """
    static_dir: str
    vectorstore: Any
    llm: Any
    thread_pool: ThreadPoolExecutor
    context_expansion_window: int  # Mutable - can be updated in get_rag()
    relevance_cache: Dict[str, bool]  # Shared cache for relevance checks
    csv_cache: Dict[str, str]  # Shared cache for CSV markdown conversions
