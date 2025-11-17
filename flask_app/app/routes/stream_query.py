# app/routes/stream.py

from flask import Blueprint, request, Response, stream_with_context, jsonify, current_app, g
import asyncio
import json
import re
from typing import List
from ..service import FilterService, StreamHandler, MetadataService, PromptService, ValidationService
from ..service.chat_history import get_history
stream_bp = Blueprint('stream', __name__, url_prefix='/api')

def _parse_int(raw, default):
    try:
        return int(raw)
    except Exception:
        return int(default)

def get_msg_hist(session_id: str) -> List[str]:
    """
    Get conversation context from the last N exchanges (human-AI pairs) for continuation detection
    Returns both human and AI messages in conversation order
    """
    if not session_id:
        return []
    try:
        history = get_history(session_id)
        if not history.messages:
            return []
        # InMemoryHistory already handles MEMORY_EXCHANGES trimming, so just format messages
        conversation_context = []
        for msg in history.messages:
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                if msg.type == 'human':
                    conversation_context.append(f"Human: {msg.content}")
                elif msg.type == 'ai' or 'ai' in msg.type.lower():
                    conversation_context.append(f"AI: {msg.content}")
        return conversation_context
    except Exception as e:
        print(f"[CONTEXT ERROR] Failed to get conversation context: {e}")
        return []

@stream_bp.route('/query', methods=['GET', 'POST'])
def query():
    """
    SSE streaming endpoint.

    Query params / JSON body:
      - query: string (required)
      - query_types: "all" | "image" | "table" | "text" | ["image","table"]  (checkbox-style)
      - year: "2024" | "2025" | None
      - top_k: int
      - context_expansion_window: int

    Examples:
      GET  /api/query?query=hello&query_types=["image","table"]&year=2025
      GET  /api/query?query=hello&query_types=image,table&year=2025
      POST {"query":"hello","query_types":["image","table"],"year":"2025"}
    """
    from ..model import Filter, Year
    
    # Validate request using ValidationService
    validated_params, error_msg = ValidationService.validate_api_request()
    
    if error_msg:
        return jsonify({"error": error_msg}), 400
    
    # Extract validated parameters
    query = validated_params['query']
    query_types = validated_params['query_types']
    year = validated_params['year']
    top_k = validated_params['top_k']
    context_expansion_window = validated_params['context_expansion_window']

    def generate_stream():
        try:
            # Initialize services
            context_expansion_window=current_app.config["DEFAULT_CONTEXT_EXPANSION_WINDOW"]
            router = current_app.router_agent
            filter_service = FilterService(
                static_dir=current_app.static_folder,
                vectorstore=current_app.vector_db,
                llm=current_app.agent,
                context_expansion_window=context_expansion_window,
                max_workers=15
            )
            stream_handler = StreamHandler(current_app.stream_agent)
            metadata_service = MetadataService()
            prompt_service = PromptService()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                previous_conversation = get_msg_hist(g.session_id)
                router_result = loop.run_until_complete(
                    router.get_action(query, previous_conversation)
                )
                print(f"[ROUTER DEBUG] Action: {router_result['action']}")
                if router_result['action'] == 'no_rag':
                    from langchain_core.messages import HumanMessage
                    from ..service.chat_history import get_history
                    history = get_history(g.session_id)
                    original_message = HumanMessage(content=query)  # Store original user input
                    history.add_messages([original_message])
                    no_rag_prompt = loop.run_until_complete(
                        prompt_service.build_no_rag_prompt(
                            original_query=query,
                            what_to_clarify=router_result.get('what_to_clarify')
                        )
                    )
                    
                    yield 'data: {"type":"stream_start"}\n\n'
                    stream_gen = stream_handler.stream_from_prompt(no_rag_prompt, session_id=g.session_id)
                    while True:
                        try:
                            chunk = loop.run_until_complete(stream_gen.__anext__())
                            yield f'data: {json.dumps({"type":"chunk","data":chunk})}\n\n'
                        except StopAsyncIteration:
                            break

                    yield 'data: {"type":"stream_end"}\n\n'
                    return

                # Step 3B: RAG path - use optimized query for search, expanded for prompt
                yield 'data: {"type":"status","message":"Fetching relevant information..."}\n\n'
                yield f'data: {json.dumps({"type":"status","message":"filters", "data": {"query_types": query_types, "year": year, "top_k": top_k, "cew": context_expansion_window}})}\n\n'

                # Use RAG-optimized query for vector search with error handling
                try:
                    rag_result = loop.run_until_complete(filter_service.get_rag(
                        query=router_result['rag_optimized_query'],  # Optimized for vector search
                        query_types=query_types,
                        year=year,
                        top_k=top_k,
                        context_expansion_window=context_expansion_window,
                        relevance_query=router_result['expanded_query'],  # Full question for relevance
                    ))

                    # Check if context is empty or None
                    context_content = rag_result.get('context', '').strip() if rag_result else ''

                    rag_prompt = loop.run_until_complete(
                        prompt_service.build_rag_prompt(
                            query=router_result['expanded_query'],  # Full proper question
                            retrieved_content=context_content if context_content else None
                        )
                    )
                except Exception as rag_error:
                    print(f"[RAG ERROR] RAG retrieval failed: {rag_error}")
                    # Fallback to no-context prompt
                    rag_prompt = loop.run_until_complete(
                        prompt_service.build_rag_prompt(
                            query=router_result['expanded_query'],
                            retrieved_content=None
                        )
                    )
                    rag_result = {'context': '', 'filter_message': f'RAG Error: {str(rag_error)}'}

                metadata_task = metadata_service.prepare_metadata_from_rag(rag_result)
                metadata_future = None
                if metadata_task:
                    metadata_future = loop.create_task(
                        metadata_service.process_metadata_async(metadata_task.task_id)
                    )

                # Manually add original query to history before sending RAG prompt
                from langchain_core.messages import HumanMessage
                from ..service.chat_history import get_history
                history = get_history(g.session_id)
                original_message = HumanMessage(content=query)  # Store original user input
                history.add_messages([original_message])
                
                # Stream the response
                yield 'data: {"type":"stream_start"}\n\n'
                stream_gen = stream_handler.stream_from_prompt(rag_prompt, session_id=g.session_id)
                while True:
                    try:
                        chunk = loop.run_until_complete(stream_gen.__anext__())
                        yield f'data: {json.dumps({"type":"chunk","data":chunk})}\n\n'
                    except StopAsyncIteration:
                        break

                # Handle metadata results
                if metadata_future:
                    try:
                        result = loop.run_until_complete(metadata_future)
                        if result:
                            metadata = {
                                'csv_tables': [csv.__dict__ for csv in result.csv_tables],
                                'processed_images': [img.__dict__ for img in result.processed_images],
                                'references': [ref.__dict__ for ref in result.references]
                            }
                            yield f'data: {json.dumps({"type":"metadata","data":metadata})}\n\n'
                        metadata_service.cleanup_task(metadata_task.task_id)
                    except Exception as e:
                        print(f"Metadata processing failed: {e}")
                        empty_meta = {"csv_tables": [], "processed_images": [], "references": []}
                        yield f'data: {json.dumps({"type":"metadata","data":empty_meta})}\n\n'
                        if metadata_task:
                            metadata_service.cleanup_task(metadata_task.task_id)
                else:
                    empty_meta = {"csv_tables": [], "processed_images": [], "references": []}
                    yield f'data: {json.dumps({"type":"metadata","data":empty_meta})}\n\n'

                # Send filter info
                yield f'data: {json.dumps({"type":"status","message": rag_result.get("filter_message","")})}\n\n'
                yield 'data: {"type":"stream_end"}\n\n'

            finally:
                # Properly close the loop and handle any remaining tasks
                try:
                    if loop and not loop.is_closed():
                        # Cancel all pending tasks
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        loop.close()
                except Exception as cleanup_error:
                    print(f"[CLEANUP ERROR] {cleanup_error}")
        except Exception as e:
            print(f"Stream error: {e}")
            # Return raw error message
            yield f'data: {json.dumps({"type":"error","message":str(e)})}\n\n'

    return Response(
        stream_with_context(generate_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )
