# app/service/filter_service.py

import os
import asyncio
import json
import re
from typing import Any, Dict, List, Tuple, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from app.model.enums import Filter, Year
from app.utils import csv_to_markdown, _deduplicate_and_join_text


class FilterService:
    def __init__(self, static_dir: str, vectorstore, llm, context_expansion_window: int = 5, max_workers: int = 8):
        self.static_dir = static_dir
        self.vectorstore = vectorstore
        self.llm = llm
        self.context_expansion_window = max(1, int(context_expansion_window))
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        self._relevance_cache: Dict[str, bool] = {}
        self._csv_cache: Dict[str, str] = {}   # key: resolved_path, val: markdown
    # =========================
    # Vectorstore filter build
    # =========================

    def build_filter(self, modalities: Union[str, List[str], None] = None,
                     year: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """Build MongoDB filter with correct INTERSECTION logic and always-include rules"""
        query_types = (modalities or "all").lower() if isinstance(modalities, str) else "all"
        year_key = year.upper() if year else None

        # Build type filter with TENDIK always included directly in $in array
        type_conditions = []
        if query_types == "text":
            type_conditions = [Filter.TEXT.value]
        elif query_types == "image":
            type_conditions = [Filter.IMAGE.value]
        elif query_types == "table":
            type_conditions = [Filter.ROW_TAB.value, Filter.CAP_TAB.value]
        elif query_types == "all":
            type_conditions = [Filter.TEXT.value, Filter.IMAGE.value, Filter.ROW_TAB.value, Filter.CAP_TAB.value]

        # Always include ROW_TENDIK directly in the type conditions
        if type_conditions:
            type_conditions.append(Filter.TENDIK.value)
            type_filter = {"type": {"$in": type_conditions}}
        else:
            # Fallback for empty conditions
            type_filter = {"type": {"$exists": True}}
        # Build year filter with GENERAL always included
        year_filter = None
        if year_key in [Year.YEAR_SARJANA.value, Year.YEAR_MAGISTER.value, Year.YEAR_DOKTOR.value]:
            year_filter = {
                "$or": [
                    {"year": year_key},
                    {"year": Year.YEAR_GENERAL.value}
                ]
            }

        # Combine filters with INTERSECTION (AND) logic
        conditions = [type_filter]
        if year_filter:
            conditions.append(year_filter)

        # Always exclude LAMPIRAN
        # conditions.append({"chapter": {"$ne": "LAMPIRAN"}})

        # Final filter structure
        final_filter = {"$and": conditions}

        # Build description
        desc_parts = []
        if query_types != "all":
            desc_parts.append(f"Types: {query_types}")
        if year_key:
            desc_parts.append(f"Year: {year_key}")
        desc_parts.append("+ TENDIK always")
        desc_parts.append("+ GENERAL always")

        filter_msg = " | ".join(desc_parts)

        return final_filter, filter_msg

    async def similarity_search(self, query: str, k: int, where: Dict[str, Any]):
        loop = asyncio.get_event_loop()

        def run():
            try:
                col = self.vectorstore._collection
                if hasattr(col, "count") and col.count(where=where or None) == 0:
                    return []
            except Exception:
                pass
            return self.vectorstore.similarity_search_with_score(query, k=k, filter=where or None)
        return await loop.run_in_executor(self.thread_pool, run)

    def group_by_modality(self, hits: List[Tuple[Document, float]]) -> Dict[str, List[Tuple[Document, float]]]:
        groups: Dict[str, List[Tuple[Document, float]]] = {}
        for doc, score in hits:
            doc.metadata["score"] = score
            groups.setdefault(doc.metadata.get("type"), []).append((doc, score))
        return groups

    # =========================
    # Strict expansion
    # =========================
    async def __batch_expand_text(self, docs: List[Document]) -> List[Document]:
        if self.context_expansion_window <= 1:
            return docs

        async def expand_one(doc: Document) -> List[Document]:
            if doc.metadata.get("type") != Filter.TEXT.value:
                return [doc]
            idx = int(doc.metadata["chunk_index"])
            total = int(doc.metadata["total_chunks_in_section"])
            section_id = doc.metadata["section_id"]
            w = self.context_expansion_window
            half = w // 2
            start = max(0, idx - half)
            end = min(total, idx + half + 1)
            if (end - start) < w:
                if start == 0:
                    end = min(total, w)
                elif end == total:
                    start = max(0, total - w)
            target_ids = [f"{section_id}_chunk_{i:03d}" for i in range(start, end)]
            expanded_docs = await self.__batch_fetch_chunks(target_ids, float(doc.metadata.get("score", 0.0)))
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

    async def __batch_fetch_chunks(self, chunk_ids: List[str], score: float) -> List[Document]:
        if not chunk_ids:
            return []
        loop = asyncio.get_event_loop()

        def fetch(batch_ids: List[str]) -> List[Document]:
            return self.vectorstore.similarity_search(query="", k=len(batch_ids) * 2, filter={"id": {"$in": batch_ids}})
        batches = [chunk_ids[i:i + 12] for i in range(0, len(chunk_ids), 12)]
        results = await asyncio.gather(*[loop.run_in_executor(self.thread_pool, fetch, b) for b in batches])
        all_docs = [d for r in results for d in r]
        by_id = {d.metadata.get("id"): d for d in all_docs}
        ordered: List[Document] = []
        for cid in chunk_ids:
            d = by_id.get(cid)
            if d:
                d.metadata["score"] = score
                ordered.append(d)
        return ordered
    # =========================
    # CSV batching with static_dir
    # =========================

    def __resolve_csv_path(self, p: str) -> str:
        if not p:
            return p
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(self.static_dir, p))

    def __load_csv_md_cached(self, resolved_path: str) -> str:
        cached = self._csv_cache.get(resolved_path)
        if cached is not None:
            return cached
        md = csv_to_markdown(resolved_path)  # expected I/O; let it raise if broken
        self._csv_cache[resolved_path] = md
        return md

    async def __batch_load_csv(self, docs: List[Document]) -> Dict[str, str]:
        orig_paths = {doc.metadata["csv_path"] for doc in docs if doc.metadata.get("csv_path")}
        if not orig_paths:
            return {}
        loop = asyncio.get_event_loop()

        def load_one(orig: str) -> Tuple[str, str]:
            resolved = self.__resolve_csv_path(orig)
            return orig, self.__load_csv_md_cached(resolved)

        results = await asyncio.gather(*[
            loop.run_in_executor(self.thread_pool, load_one, p) for p in sorted(orig_paths)
        ])
        return dict(results)

    # =========================
    # Content building (exact)
    # =========================
    async def __batch_build_content(self, docs: List[Document], include_full_table: bool = True) -> List[str]:
        csv_md_map = await self.__batch_load_csv(docs)

        def one(doc: Document) -> str:
            doc_type = doc.metadata.get('type')
            csv_path = doc.metadata.get('csv_path')
            section_title = doc.metadata.get('section_title')
            caption = doc.metadata.get('caption', '')
            #
            if doc_type == Filter.TEXT.value:
                content = doc.page_content
                # Add section title for text content during expansion
                if section_title:
                    content = f"{content}\nSection: {section_title}"
            elif doc_type == Filter.TENDIK.value:
                content = doc.page_content
                # Check for pairs metadata first
                pairs_data = doc.metadata.get('pairs')
                pair_data = doc.metadata.get('pair')
                if pairs_data:
                    print("CAPTION")
                else:
                    print("ROWDATA")
                
                if pairs_data:  # If pairs exist, format as table caption
                    content = f"Table Caption: {caption}\n{content}"
                    if csv_path:
                        md_table = csv_md_map.get(csv_path, "")
                        if include_full_table:
                            content += f"\nFull Table: {caption}\n{md_table}"
                        else:
                            content += f"\nTable Preview: {caption}\n{md_table[:200]}..."
                elif pair_data:  # If only pair exists, format as staff data
                    content = f"Staff Data: {caption}\n{content}"
                    if csv_path:
                        md_table = csv_md_map.get(csv_path, "")
                        if include_full_table:
                            content += f"\n{md_table}"
                        else:
                            content += f"\n{md_table[:200]}..."
                else:  # Fallback if neither pairs nor pair exist
                    if csv_path:
                        md_table = csv_md_map.get(csv_path, "")
                        if include_full_table:
                            content = f"Staff Data: {caption}\n{content}\n{md_table}"
                        else:
                            content = f"Staff Data: {caption}\n{content}\n{md_table[:200]}..."
            elif doc_type == Filter.ROW_TAB.value:
                content = doc.page_content
                if csv_path:
                    md_table = csv_md_map.get(csv_path, "")
                    if include_full_table:
                        content = f"Table: {caption}\n{content}\n{md_table}"
                    else:
                        content = f"Table: {caption}\n{content}\n{md_table[:200]}..."
            elif doc_type == Filter.IMAGE.value:
                content = f"Konten Mengandung gambar , {caption}"
            elif doc_type == Filter.CAP_TAB.value:
                content = f"Table Caption: {caption}"
                
                if csv_path:
                    md_table = csv_md_map.get(csv_path, "")
                    if include_full_table:
                        content += f" \n Full Table: {caption}\n{md_table}"
                    else:
                        content += f" \n Table Preview: {caption}\n{md_table[:200]}..."
            else:
                content = doc.page_content

            return f"{str(content)}\nsection title: {section_title}" if section_title else str(content)

        return [one(d) for d in docs]

    def __get_cache_key(self, doc: Document, query: str) -> str:
        return f"{doc.metadata.get('id', '')}:{hash(query.lower().strip())}"

    async def __batch_relevance_check(self, doc: Document, query: str) -> Tuple[bool, str]:
        content = await self.__batch_build_content([doc], include_full_table=False)
        prompt = f"""
        
        Tugas: Tentukan apakah konten berikut relevan dengan pertanyaan.
        Konteks: anda adalah penentu relevansi untuk konteks RAG anda runngin secara pararel dengan instance2 yang lain 
        Konten: {content[0]}
        Pertanyaan: {query}
        Instruksi:
        1. Analisis apakah konten **SECARA LANGSUNG atau PARSIAL** dapat menjawab atau relevan dengan pertanyaan, tolong pikirkan dengan baik apakah konten yang di maksud 
        relevan dengan pertanyaan jika tidak relevan maka kembalikan false
        MENJAWAB PARSIAL HANYA BERLAKU JIKA PERTANYAAN MERUPAKAN PERTANYAAN KOMPOSIT (NAMUN TIDAK BOLEH IMPLISIT HARUS EKSPLISIT)
        ATAU PERTANYAAN YANG SANGAT GENERAL dan KONTEN yang di sajikan rasanya dapat membantu menjawab
        pertanyaan secara sebagian. 
        2. Berikan respons Anda dalam format JSON yang KETAT dengan bidang-bidang berikut:
        3. tolong jangan berbias di kolom explanation 
        4. Setelah di cek kemudian baru di cek apakah relevan atau tidak relevan berdasarkan explanation yang dibuat
        5. Khusus untuk Pertanyaaan dosen jika general tolong hanya filter bagian yang sangat relevan
        daftar : 
            Tabel dosen teknik mesin dan industri FT UGM -> jika menanyakan Mengenai Dosen secara general 
            Tabel Kepala Laboratorium Departemen teknik mesi dan industri -> Jika menanyakan hal2 yang terkait dengan laboratorium 
            Tabel Professor Kepala laboratorium DTMI -> Jika menanyakan mengenai Professor UGM 
            Tabel dosen Pranatugas -> Jika menanayakan mengenai Dosen Pranatugas 
            Tabel Pengurus -> ada spesifik antara (Sarjana, Magister dan Doktor ) Jika memang tidak terdapat filter spesifik loloskan semua 
        Tabel dosen != Tabel Professor.
        Jika item merupakan sebuah tabel Lebih baik. Disampaikan secara list. 
           {{
             "explanation": "Jelaskan mengapa konten ini relevan atau tidak relevan dengan pertanyaan maks 2 kalimat",
             "is_relevant": true atau false
           }}
        PENTING: Kembalikan HANYA objek JSON tanpa teks tambahan sebelum tau sesudah.
        """
        prompt = HumanMessage(content=prompt)
        response = await self.llm.ainvoke([prompt])
        response_text = str(response.content if hasattr(response, 'content') else response)
        # print(f"[RELEVANCE DEBUG] Raw LLM response: '{response_text}'")
        try:
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if not json_match:
                raise ValueError("no json found in response")
            json_str = json_match.group(0)
            result = json.loads(json_str)
            is_relevant = result.get("is_relevant", False)
            explanation = result.get("explanation", "")
            return is_relevant, explanation
        except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
            print(f"[RELEVANCE ERROR] Failed to parse relevance response: {e}")
            # print(f"[RELEVANCE ERROR] Raw response: {response_text}")
            # Fallback - mark as not relevant with fallback message
            return False, "Mohon maaf, data sedang tidak tersedia. Mohon hubungi pengelola."

    async def evaluate_relevance(self, docs_to_process: List[Tuple], query: str) -> List[Tuple]:
        if not docs_to_process:
            return []
        cache_results, uncached = [], []
        for doc, score in docs_to_process:
            cache_key = self.__get_cache_key(doc, query)
            cached_result = self._relevance_cache.get(cache_key)
            if cached_result is not None:
                if cached_result:
                    cache_results.append((doc, score))
            else:
                uncached.append((doc, score))
        if not uncached:
            return cache_results
        sem = asyncio.Semaphore(16)

        async def eval_one(doc: Document, score: float):
            async with sem:
                relevant, explanation = await asyncio.wait_for(self.__batch_relevance_check(doc, query), timeout=15)
                cache_key = self.__get_cache_key(doc, query)
                self._relevance_cache[cache_key] = relevant

                if relevant:
                    doc.metadata['explanation'] = explanation
                    return (doc, score)
                return None
        eval_results = await asyncio.gather(*[eval_one(doc, score) for doc, score in uncached])
        valid_results = [result for result in eval_results if result is not None]
        return cache_results + valid_results

    # =========================
    # Dedup identical to yours
    # =========================
    def __batch_deduplicate(self, docs_with_content: List[Tuple]) -> Tuple[List[str], List[dict], List[Tuple[str, str]], List[Tuple[str, str]]]:
        all_texts, all_metadatas = [], []
        image_dict, csv_dict = {}, {}
        used_ids, used_contents = set(), set()
        used_normalized_image_captions = set()
        used_normalized_csv_captions = set()

        def normalize_caption(caption: str) -> str:

            if not caption:
                return ""
            cleaned_caption = re.sub(r'[^\w\s]', '', caption.lower())
            tokens = sorted(cleaned_caption.split())
            return " ".join(tokens)

        for doc, content in docs_with_content:
            meta = doc.metadata
            doc_id = meta.get('id')
            normalized_content = ' '.join(content.split())
        
            if (normalized_content in used_contents) or (doc_id and doc_id in used_ids):
                continue
            if doc_id:
                used_ids.add(doc_id)
            used_contents.add(normalized_content)

            score = doc.metadata.get('score', 0.0)
            prefix = f"[{doc_id}|{score:.4f}]"
            all_texts.append(f"{prefix} {content}")
            all_metadatas.append(meta)

            caption = meta.get('caption', '')
            if caption:
                normalized_caption = normalize_caption(caption)
                if normalized_caption:
                    img_path = meta.get('image_path')
                    if img_path and normalized_caption not in used_normalized_image_captions:
                        image_dict[img_path] = caption
                        used_normalized_image_captions.add(normalized_caption)
                    csv_path = meta.get('csv_path')
                    if csv_path and normalized_caption not in used_normalized_csv_captions:
                        csv_dict[csv_path] = caption
                        used_normalized_csv_captions.add(normalized_caption)

            # Extract images from TENDIK records (pair/pairs) - separate from caption logic
            if meta.get('type') == Filter.TENDIK.value:
                pair = meta.get('pair')
                if pair:
                    try:
                        # Check if pair is a string that needs to be parsed
                        if isinstance(pair, str):
                            import ast
                            pair = ast.literal_eval(pair)
                        
                        if isinstance(pair, (list, tuple)) and len(pair) == 2:
                            img_path, person_name = pair
                            if img_path and person_name:
                                person_normalized = normalize_caption(person_name)
                                if person_normalized and person_normalized not in used_normalized_image_captions:
                                    image_dict[img_path] = person_name
                                    used_normalized_image_captions.add(person_normalized)
                        else:
                            print(f"[PAIR ERROR] Expected pair with 2 elements, got {len(pair) if isinstance(pair, (list, tuple)) else 'non-list/tuple type'} elements: {pair}")
                    except (ValueError, TypeError, SyntaxError) as e:
                        print(f"[PAIR ERROR] Error processing pair {pair}: {e}")

                pairs = meta.get('pairs')
                if pairs:
                    try:
                        # Check if pairs is a string that needs to be parsed
                        if isinstance(pairs, str):
                            import ast
                            pairs = ast.literal_eval(pairs)
                        
                        # Handle pairs which is an array of pairs: [[img_path, person_name], [img_path, person_name], ...]
                        if isinstance(pairs, (list, tuple)):
                            for pair_item in pairs:
                                if isinstance(pair_item, (list, tuple)) and len(pair_item) >= 2:
                                    img_path = pair_item[0]  # First element is always the image path
                                    person_name = pair_item[1]  # Second element is always the person name
                                    if img_path and person_name:
                                        person_normalized = normalize_caption(person_name)
                                        if person_normalized and person_normalized not in used_normalized_image_captions:
                                            image_dict[img_path] = person_name
                                            used_normalized_image_captions.add(person_normalized)
                                else:
                                    print(f"[PAIRS ERROR] Expected pair_item with at least 2 elements, got: {pair_item}")
                        else:
                            print(f"[PAIRS ERROR] pairs is not a list/tuple: {pairs}")
                    except (ValueError, TypeError, SyntaxError) as e:
                        print(f"[PAIRS ERROR] Error processing pairs {pairs}: {e}")

        image_paths = list(image_dict.items())
        csv_paths = list(csv_dict.items())
        return all_texts, all_metadatas, image_paths, csv_paths

    # =========================
    # Public API
    # =========================

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
        where, _ = self.build_filter(query_types, year)
        raw_hits = await self.similarity_search(query, top_k, where)
        print(f"[FILTER DEBUG] Found {len(raw_hits)} raw hits")
        if not raw_hits:
            raise ValueError(f"RAG ERROR: No hits found for query '{query}' with filter {where}")
   
        groups = self.group_by_modality(raw_hits)

        # expand TEXT docs, keep others as-is
        all_docs: List[Tuple[Document, float]] = []
        if Filter.TEXT.value in groups:
            text_docs = [doc for doc, _ in groups[Filter.TEXT.value]]
            expanded_docs = await self.__batch_expand_text(text_docs)
            all_docs.extend([(doc, float(doc.metadata.get('score', 0.0))) for doc in expanded_docs])

        for t, arr in groups.items():
            if t != Filter.TEXT.value:
                all_docs.extend(arr)
        # print(f"[FILTER DEBUG] Using relevance query: '{relevance_query}'")
        relevant_docs = await self.evaluate_relevance(all_docs, relevance_query) if all_docs else []
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
        content_texts = await self.__batch_build_content(docs, include_full_table=True)
        docs_with_content = list(zip(docs, content_texts))
        all_texts, all_metadatas, image_paths, csv_paths = self.__batch_deduplicate(docs_with_content)
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
