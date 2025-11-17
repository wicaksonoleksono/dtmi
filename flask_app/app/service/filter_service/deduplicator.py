# app/service/filter_service/deduplicator.py

import re
from typing import List, Tuple, Dict, Set
from langchain_core.documents import Document
from app.model.enums import Filter


def batch_deduplicate(docs_with_content: List[Tuple]) -> Tuple[List[str], List[dict], List[Tuple[str, str]], List[Tuple[str, str]]]:
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
