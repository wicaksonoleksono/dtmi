# app/service/filter_service/content_builder.py

from typing import List, Dict
from langchain_core.documents import Document
from app.model.enums import Filter
from .dependencies import FilterServiceDeps
from .csv_handler import batch_load_csv


async def batch_build_content(deps: FilterServiceDeps, docs: List[Document], include_full_table: bool = True) -> List[str]:
    csv_md_map = await batch_load_csv(deps, docs)

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
