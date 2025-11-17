# app/service/filter_service/__init__.py

import os
from typing import Any, Dict, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document

from .dependencies import FilterServiceDeps
from .filter_builder import build_filter
from .vector_search import similarity_search, group_by_modality
from .context_expansion import batch_expand_text
from .content_builder import batch_build_content
from .relevance_evaluator import evaluate_relevance
from .deduplicator import batch_deduplicate
from app.model.enums import Filter


class FilterService:
    def __init__(self, static_dir: str, vectorstore, llm, context_expansion_window: int = 5, max_workers: int = 8):
        self.static_dir = static_dir
        self.vectorstore = vectorstore
        self.llm = llm
        self.context_expansion_window = max(1, int(context_expansion_window))
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        self._relevance_cache: Dict[str, bool] = {}
        self._csv_cache: Dict[str, str] = {}   # key: resolved_path, val: markdown

    def _get_deps(self) -> FilterServiceDeps:
        """Create dependencies object with current state"""
        return FilterServiceDeps(
            static_dir=self.static_dir,
            vectorstore=self.vectorstore,
            llm=self.llm,
            thread_pool=self.thread_pool,
            context_expansion_window=self.context_expansion_window,
            relevance_cache=self._relevance_cache,
            csv_cache=self._csv_cache
        )

    async def get_rag(
        self,
        query: str,
        query_types: Union[str, List[str]] = "all",
        year: Optional[str] = None,
        top_k: int = 20,
        context_expansion_window: Optional[int] = None,
        relevance_query: Optional[str] = None,  # For relevance checking if different from search query
    ) -> Dict[str, Any]:
        if context_expansion_window is not None:
            self.context_expansion_window = max(1, int(context_expansion_window))

        deps = self._get_deps()

        where, _ = build_filter(query_types, year)
        raw_hits = await similarity_search(deps, query, top_k, where)
        print(f"[FILTER DEBUG] Found {len(raw_hits)} raw hits \n{context_expansion_window}")
        if not raw_hits:
            raise ValueError(f"RAG ERROR: No hits found for query '{query}' with filter {where}")

        groups = group_by_modality(raw_hits)

        # expand TEXT docs, keep others as-is
        all_docs: List[tuple[Document, float]] = []
        if Filter.TEXT.value in groups:
            text_docs = [doc for doc, _ in groups[Filter.TEXT.value]]
            expanded_docs = await batch_expand_text(deps, text_docs)
            all_docs.extend([(doc, float(doc.metadata.get('score', 0.0))) for doc in expanded_docs])

        for t, arr in groups.items():
            if t != Filter.TEXT.value:
                all_docs.extend(arr)
        # print(f"[FILTER DEBUG] Using relevance query: '{relevance_query}'")
        relevant_docs = await evaluate_relevance(deps, all_docs, relevance_query) if all_docs else []
        # print(f"[FILTER DEBUG] After relevance filtering: {len(relevant_docs)} docs")
        seen, deduped = set(), []
        for doc, score in relevant_docs:
            key = doc.metadata.get('csv_path') or doc.metadata.get('id', '')
            if key not in seen:
                seen.add(key)
                deduped.append((doc, score))

        # print(f"[FILTER DEBUG] After deduplication: {len(deduped)} docs")
        # if deduped:
        #     print(f"[FILTER DEBUG] Final docs chapters: {[doc.metadata.get('chapter') for doc, _ in deduped[:5]]}")

        docs = [d for d, _ in deduped]
        content_texts = await batch_build_content(deps, docs, include_full_table=True)
        docs_with_content = list(zip(docs, content_texts))
        all_texts, all_metadatas, image_paths, csv_paths = batch_deduplicate(docs_with_content)
        image_paths = [(os.path.join(self.static_dir, p), caption) for p, caption in image_paths]
        csv_paths = [(os.path.join(self.static_dir, p), caption) for p, caption in csv_paths]
        combined_context = "\n\n".join(all_texts)
        return {
            'context': combined_context,
            'image_paths': image_paths,
            'csv_paths': csv_paths,
            'metadatas': all_metadatas,
            'csv_content': {},  # CSV already embedded in context
            'query_type_used': query_types,
            'filter_message': f"auto where: {where}",
        }
