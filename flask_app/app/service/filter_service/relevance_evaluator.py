# app/service/filter_service/relevance_evaluator.py

import asyncio
import json
import re
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from .dependencies import FilterServiceDeps
from .content_builder import batch_build_content


def get_cache_key(doc: Document, query: str) -> str:
    return f"{doc.metadata.get('id', '')}:{hash(query.lower().strip())}"


async def batch_relevance_check(deps: FilterServiceDeps, doc: Document, query: str) -> Tuple[bool, str]:
    content = await batch_build_content(deps, [doc], include_full_table=False)
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
         "rationale": "Jelaskan mengapa konten ini relevan atau tidak relevan dengan pertanyaan maks 2 kalimat",
         "is_relevant": true atau false
       }}
    PENTING: Kembalikan HANYA objek JSON tanpa teks tambahan sebelum tau sesudah.
    """
    prompt = HumanMessage(content=prompt)
    response = await deps.llm.ainvoke([prompt])
    response_text = str(response.content if hasattr(response, 'content') else response)
    print(f"[shit]:{content[0]}\n[Resp]: '{response_text}'")
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


async def evaluate_relevance(deps: FilterServiceDeps, docs_to_process: List[Tuple], query: str) -> List[Tuple]:
    if not docs_to_process:
        return []
    cache_results, uncached = [], []
    for doc, score in docs_to_process:
        cache_key = get_cache_key(doc, query)
        cached_result = deps.relevance_cache.get(cache_key)
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
            relevant, explanation = await asyncio.wait_for(batch_relevance_check(deps, doc, query), timeout=15)
            cache_key = get_cache_key(doc, query)
            deps.relevance_cache[cache_key] = relevant

            if relevant:
                doc.metadata['explanation'] = explanation
                return (doc, score)
            return None
    eval_results = await asyncio.gather(*[eval_one(doc, score) for doc, score in uncached])
    valid_results = [result for result in eval_results if result is not None]
    return cache_results + valid_results
