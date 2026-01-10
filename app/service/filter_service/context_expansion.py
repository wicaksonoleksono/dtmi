# app/service/filter_service/context_expansion.py

import asyncio
from typing import List, Tuple
from langchain_core.documents import Document
from app.model.enums import Filter
from app.utils import _deduplicate_and_join_text
from .dependencies import FilterServiceDeps


async def batch_expand_text(deps: FilterServiceDeps, docs: List[Document]) -> List[Document]:
    if deps.context_expansion_window <= 1:
        return docs

    async def expand_one(doc: Document) -> List[Document]:
        if doc.metadata.get("type") != Filter.TEXT.value:
            return [doc]
        idx = int(doc.metadata["chunk_index"])
        total = int(doc.metadata["total_chunks_in_section"])
        section_id = doc.metadata["section_id"]
        w = deps.context_expansion_window
        half = w // 2
        start = max(0, idx - half)
        end = min(total, idx + half + 1)
        if (end - start) < w:
            if start == 0:
                end = min(total, w)
            elif end == total:
                start = max(0, total - w)
        target_ids = [f"{section_id}_chunk_{i:03d}" for i in range(start, end)]
        expanded_docs = await batch_fetch_chunks(deps, target_ids, float(doc.metadata.get("score", 0.0)))
        if len(expanded_docs) > 1:
            merged = _deduplicate_and_join_text(expanded_docs)
            return [Document(page_content=merged, metadata=doc.metadata.copy())]
        return [doc]
    results = await asyncio.gather(*[expand_one(d) for d in docs])
    expanded_docs = [d for batch in results for d in batch]

    # Fast deduplication using chunk IDs instead of content comparison
    seen_ids = set()
    deduped_docs = []

    for doc in expanded_docs:
        doc_id = doc.metadata.get('id')
        if doc_id and doc_id not in seen_ids:
            seen_ids.add(doc_id)
            deduped_docs.append(doc)
        elif not doc_id:
            continue

    return deduped_docs


async def batch_fetch_chunks(deps: FilterServiceDeps, chunk_ids: List[str], score: float) -> List[Document]:
    if not chunk_ids:
        return []
    loop = asyncio.get_event_loop()

    def fetch(batch_ids: List[str]) -> List[Document]:
        return deps.vectorstore.similarity_search(query="", k=len(batch_ids) * 2, filter={"id": {"$in": batch_ids}})
    batches = [chunk_ids[i:i + 12] for i in range(0, len(chunk_ids), 12)]
    results = await asyncio.gather(*[loop.run_in_executor(deps.thread_pool, fetch, b) for b in batches])
    all_docs = [d for r in results for d in r]
    by_id = {d.metadata.get("id"): d for d in all_docs}
    ordered: List[Document] = []
    for cid in chunk_ids:
        d = by_id.get(cid)
        if d:
            d.metadata["score"] = score
            ordered.append(d)
    return ordered
