# app/service/filter_service/csv_handler.py

import os
import asyncio
from typing import Dict, List, Tuple
from langchain_core.documents import Document
from app.utils import csv_to_markdown
from .dependencies import FilterServiceDeps


def resolve_csv_path(deps: FilterServiceDeps, p: str) -> str:
    if not p:
        return p
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(deps.static_dir, p))


def load_csv_md_cached(deps: FilterServiceDeps, resolved_path: str) -> str:
    cached = deps.csv_cache.get(resolved_path)
    if cached is not None:
        return cached
    md = csv_to_markdown(resolved_path)  # expected I/O; let it raise if broken
    deps.csv_cache[resolved_path] = md
    return md


async def batch_load_csv(deps: FilterServiceDeps, docs: List[Document]) -> Dict[str, str]:
    orig_paths = {doc.metadata["csv_path"] for doc in docs if doc.metadata.get("csv_path")}
    if not orig_paths:
        return {}
    loop = asyncio.get_event_loop()

    def load_one(orig: str) -> Tuple[str, str]:
        resolved = resolve_csv_path(deps, orig)
        return orig, load_csv_md_cached(deps, resolved)

    results = await asyncio.gather(*[
        loop.run_in_executor(deps.thread_pool, load_one, p) for p in sorted(orig_paths)
    ])
    return dict(results)
