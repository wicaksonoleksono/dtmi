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
from .relevance_evaluator import batch_relevance_check, filter_docs_by_ids
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
        """
        NEW BATCHED FLOW:
        1. Vector search + expand
        2. Build PREVIEW content for ALL docs
        3. Single batch relevance check (1 LLM call)
        4. Filter by IDs
        5. Rebuild FULL content for relevant docs only
        6. Deduplicate
        """
        if context_expansion_window is not None:
            self.context_expansion_window = max(1, int(context_expansion_window))

        deps = self._get_deps()
        # Step 1: Vector search
        where, _ = build_filter(query_types, year)
        raw_hits = await similarity_search(deps, query, top_k, where)
        print(f"[FILTER DEBUG] Found {len(raw_hits)} raw hits")
        if not raw_hits:
            raise ValueError(f"RAG ERROR: No hits found for query '{query}' with filter {where}")
        groups = group_by_modality(raw_hits)
        # Step 2: Expand TEXT docs, keep others as-is
        all_docs: List[tuple[Document, float]] = []
        if Filter.TEXT.value in groups:
            text_docs = [doc for doc, _ in groups[Filter.TEXT.value]]
            expanded_docs = await batch_expand_text(deps, text_docs)
            all_docs.extend([(doc, float(doc.metadata.get('score', 0.0))) for doc in expanded_docs])
        for t, arr in groups.items():
            if t != Filter.TEXT.value:
                all_docs.extend(arr)
        if not all_docs:
            raise ValueError("No documents after expansion")
        print(f"[FILTER DEBUG] After expansion: {len(all_docs)} docs")
        # Step 3: Build PREVIEW content for ALL docs (include_full_table=False to save tokens)
        docs_only = [doc for doc, _ in all_docs]
        preview_contents = await batch_build_content(deps, docs_only, include_full_table=False)
        docs_with_preview = list(zip(docs_only, preview_contents))
        print(f"[FILTER DEBUG] Built preview content for {len(docs_with_preview)} docs")
        # Step 4: BATCH relevance check (1 LLM call for ALL documents)
        relevance_evaluation = await batch_relevance_check(
            deps,
            docs_with_preview,
            relevance_query or query
        )
        print(f"[FILTER DEBUG] Batch relevance: {relevance_evaluation.rationale}")
        print(f"[FILTER DEBUG] Selected IDs: {relevance_evaluation.ids}")
        # Step 5: Filter docs by relevant IDs
        relevant_docs = filter_docs_by_ids(docs_with_preview, relevance_evaluation)

        if not relevant_docs:
            print("[FILTER WARNING] No relevant docs after batch filtering")
            # Return empty result
            return {
                'context': '',
                'image_paths': [],
                'csv_paths': [],
                'metadatas': [],
                'csv_content': {},
                'query_type_used': query_types,
                'filter_message': f"No relevant documents found. Filter: {where}",
            }
        print(f"[FILTER DEBUG] After batch relevance: {len(relevant_docs)} relevant docs")
        # Step 6: Deduplicate by csv_path/id
        seen, deduped = set(), []
        for doc, score in relevant_docs:
            key = doc.metadata.get('csv_path') or doc.metadata.get('id', '')
            if key not in seen:
                seen.add(key)
                deduped.append((doc, score))

        print(f"[FILTER DEBUG] After first dedup: {len(deduped)} docs")
        # Step 7: Rebuild FULL content for filtered docs ONLY (include_full_table=True)
        docs_filtered = [d for d, _ in deduped]
        full_contents = await batch_build_content(deps, docs_filtered, include_full_table=True)
        docs_with_full_content = list(zip(docs_filtered, full_contents))
        print(f"[FILTER DEBUG] Rebuilt FULL content for {len(docs_with_full_content)} relevant docs")
        # Step 8: Final deduplication + extract metadata
        all_texts, all_metadatas, image_paths, csv_paths = batch_deduplicate(docs_with_full_content)
        image_paths = [(os.path.join(self.static_dir, p), caption) for p, caption in image_paths]
        csv_paths = [(os.path.join(self.static_dir, p), caption) for p, caption in csv_paths]
        combined_context = "\n\n".join(all_texts)
        print(f"[FILTER DEBUG] Final: {len(all_texts)} text blocks, {len(image_paths)} images, {len(csv_paths)} CSVs")

        return {
            'context': combined_context,
            'image_paths': image_paths,
            'csv_paths': csv_paths,
            'metadatas': all_metadatas,
            'csv_content': {},  # CSV already embedded in context
            'query_type_used': query_types,
            'filter_message': f"Batch relevance: {relevance_evaluation.rationale[:100]}... | Filter: {where}",
        }
