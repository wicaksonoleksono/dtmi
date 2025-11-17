# app/service/filter_service/vector_search.py

import asyncio
from typing import Any, Dict, List, Tuple
from langchain_core.documents import Document
from .dependencies import FilterServiceDeps


async def similarity_search(deps: FilterServiceDeps, query: str, k: int, where: Dict[str, Any]) -> List[Tuple[Document, float]]:
    loop = asyncio.get_event_loop()

    def run():
        try:
            col = deps.vectorstore._collection
            if hasattr(col, "count") and col.count(where=where or None) == 0:
                return []
        except Exception:
            pass
        return deps.vectorstore.similarity_search_with_score(query, k=k, filter=where or None)
    return await loop.run_in_executor(deps.thread_pool, run)


def group_by_modality(hits: List[Tuple[Document, float]]) -> Dict[str, List[Tuple[Document, float]]]:
    groups: Dict[str, List[Tuple[Document, float]]] = {}
    for doc, score in hits:
        doc.metadata["score"] = score
        groups.setdefault(doc.metadata.get("type"), []).append((doc, score))
    return groups
