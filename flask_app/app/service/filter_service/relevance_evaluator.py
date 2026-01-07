# app/service/filter_service/relevance_evaluator.py

import json
import re
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from .dependencies import FilterServiceDeps
from app.model.chroma_types import BatchRelevanceResponse


def format_document_with_tag(doc: Document, content: str, doc_num: int) -> str:
    """
    Format document with [docnum] tag structure (indoclimate pattern)

    Args:
        doc: LangChain Document with metadata
        content: Pre-built content string (from content_builder with preview mode)
        doc_num: Document number for tagging [1], [2], [3], etc.

    Returns:
        Formatted string: "[1]\nType: text\nsection_title: ...\nContent: ...\n---"
    """
    meta = doc.metadata
    doc_type = meta.get('type', 'unknown')
    section_title = meta.get('section_title', '') or 'N/A'
    caption = meta.get('caption', '')

    formatted = f"[{doc_num}]\n"
    formatted += f"Type: {doc_type}\n"
    formatted += f"section_title: {section_title}\n"  # ALWAYS include for context

    if caption:
        formatted += f"Caption: {caption}\n"

    formatted += f"\n{content}\n"
    formatted += "---\n"

    return formatted


async def batch_relevance_check(
    deps: FilterServiceDeps,
    docs_with_content: List[Tuple[Document, str]],
    query: str
) -> BatchRelevanceResponse:
    """
    Batch relevance checking using indoclimate pattern

    Single LLM call evaluates ALL documents at once

    Args:
        deps: FilterServiceDeps with llm
        docs_with_content: List of (Document, preview_content_string) tuples
        query: User's query for relevance checking

    Returns:
        BatchRelevanceResponse with rationale and list of relevant IDs
    """
    # Format all documents with tags
    formatted_docs = []
    for idx, (doc, content) in enumerate(docs_with_content, start=1):
        formatted = format_document_with_tag(doc, content, idx)
        formatted_docs.append(formatted)

    all_formatted = "\n".join(formatted_docs)

    # Build prompt (adapted from indoclimate + existing DTMI rules)
    prompt = f"""Tugas: Evaluasi relevansi setiap dokumen terhadap pertanyaan pengguna.

Pertanyaan: {query}

Dokumen yang tersedia:
{all_formatted}

Instruksi:
1. Analisis setiap dokumen [1], [2], [3], dst.
2. Tentukan dokumen mana yang **SECARA LANGSUNG atau PARSIAL** dapat menjawab pertanyaan
3.  MENJAWAB PARSIAL HANYA BERLAKU JIKA PERTANYAAN MERUPAKAN PERTANYAAN KOMPOSIT ATAU PERTANYAAN YANG SANGAT GENERAL dan KONTEN 
    yang di sajikan rasanya dapat membantu menjawab pertanyaan secara sebagian
4. Tolong jangan berbias di kolom rationale
5. Boleh terjawab secara implisit namun jika implisit pastikan konteks dapat terjawab.
5. Khusus untuk Pertanyaan dosen jika general tolong hanya filter bagian yang sangat relevan:
   - Tabel dosen teknik mesin dan industri FT UGM → jika menanyakan Mengenai Dosen secara general
   - Tabel Kepala Laboratorium Departemen teknik mesin dan industri → Jika menanyakan hal2 yang terkait dengan laboratorium
   - Tabel Professor Kepala laboratorium DTMI → Jika menanyakan mengenai Professor UGM
   - Tabel dosen Pranatugas → Jika menanyakan mengenai Dosen Pranatugas
   - Tabel Pengurus → ada spesifik antara (Sarjana, Magister dan Doktor) Jika memang tidak terdapat filter spesifik loloskan semua
   - Tabel dosen != Tabel Professor
6. Jika item merupakan sebuah tabel Lebih baik disampaikan secara list
7. Berikan penjelasan detail mengapa dokumen dipilih atau tidak
8. Output HARUS JSON valid dengan format:

{{
  "rationale": "penjelasan detail dokumen mana yang relevan dan mengapa (maks 3 kalimat)",
  "ids": [1, 3, 5]
}}

PENTING: Output harus JSON valid tanpa markdown/backticks."""

    prompt_message = HumanMessage(content=prompt)

    try:
        # Single LLM call for all documents
        response = await deps.llm.ainvoke([prompt_message])
        response_text = str(response.content if hasattr(response, 'content') else response)

        print(f"[BATCH RELEVANCE] Evaluated {len(docs_with_content)} documents")
        print(f"[BATCH RELEVANCE] Response preview: {response_text[:200]}...")

        # Parse JSON response (remove markdown if present)
        json_string = response_text
        json_string = re.sub(r'```json\n?', '', json_string)
        json_string = re.sub(r'```\n?', '', json_string)
        json_string = json_string.strip()

        # Extract JSON object
        json_match = re.search(r'\{.*\}', json_string, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")

        parsed = json.loads(json_match.group(0))

        result = BatchRelevanceResponse(
            rationale=parsed.get("rationale", ""),
            ids=parsed.get("ids", [])
        )

        print(f"[BATCH RELEVANCE] Selected {len(result.ids)} relevant documents: {result.ids}")
        print(f"[BATCH RELEVANCE] Rationale: {result.rationale}")

        return result

    except (json.JSONDecodeError, ValueError, KeyError, Exception) as e:
        print(f"[BATCH RELEVANCE ERROR] Failed to parse response: {e}")
        print(f"[BATCH RELEVANCE ERROR] Raw response: {response_text if 'response_text' in locals() else 'N/A'}")

        # Fallback: Return all document IDs on error
        all_ids = list(range(1, len(docs_with_content) + 1))
        return BatchRelevanceResponse(
            rationale=f"Error in evaluation, returning all documents. Error: {str(e)}",
            ids=all_ids
        )


def filter_docs_by_ids(
    docs_with_content: List[Tuple[Document, str]],
    evaluation: BatchRelevanceResponse
) -> List[Tuple[Document, float]]:
    """
    Filter documents by relevant IDs from batch evaluation

    Args:
        docs_with_content: List of (Document, content_string) tuples with 1-based indexing
        evaluation: BatchRelevanceResponse with ids=[1, 3, 5]

    Returns:
        List of (Document, score) tuples for relevant documents only
    """
    if not evaluation.ids:
        print("[FILTER WARNING] No relevant IDs selected, returning empty list")
        return []

    filtered = []
    for idx, (doc, _) in enumerate(docs_with_content, start=1):
        if idx in evaluation.ids:
            score = float(doc.metadata.get('score', 0.0))
            filtered.append((doc, score))

    print(f"[FILTER] Filtered {len(filtered)}/{len(docs_with_content)} documents")

    return filtered
