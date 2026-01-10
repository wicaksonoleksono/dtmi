"""
Chat-specific decorators for error handling and response formatting
"""

import functools
import json
import time
import asyncio
import uuid
from typing import Any, Callable, Optional, Union, Generator
from flask import jsonify, Response, stream_template, current_app, request
from langchain_core.messages import SystemMessage, HumanMessage
from ..model.chat_models import (
    ChatResponse, ErrorResponse, WebhookResponse,
    StreamingChatResponse, MetadataLoadingTask
)


def handle_chat_errors(
    error_type: str = "chat_error",
    return_json: bool = True,
    log_errors: bool = True
):
    """
    Decorator for handling chat-related errors with proper response formatting
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                start_time = time.time()
                result = await func(*args, **kwargs)

                # Add processing time if result is ChatResponse
                if hasattr(result, 'processing_time'):
                    result.processing_time = time.time() - start_time

                return jsonify(result.to_dict()) if return_json and hasattr(result, 'to_dict') else result

            except Exception as e:
                if log_errors:
                    print(f"[CHAT_ERROR] {func.__name__}: {e}")

                error_response = ErrorResponse(
                    error=str(e),
                    error_type=error_type,
                    timestamp=time.time()
                )

                if return_json:
                    return jsonify(error_response.to_dict()), 500
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                start_time = time.time()
                result = func(*args, **kwargs)

                # Add processing time if result is ChatResponse
                if hasattr(result, 'processing_time'):
                    result.processing_time = time.time() - start_time

                return jsonify(result.to_dict()) if return_json and hasattr(result, 'to_dict') else result

            except Exception as e:
                if log_errors:
                    print(f"[CHAT_ERROR] {func.__name__}: {e}")

                error_response = ErrorResponse(
                    error=str(e),
                    error_type=error_type,
                    timestamp=time.time()
                )

                if return_json:
                    return jsonify(error_response.to_dict()), 500
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def handle_webhook_errors(log_errors: bool = True):
    """
    Decorator specifically for webhook endpoints
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                start_time = time.time()
                result = await func(*args, **kwargs)

                # Add processing time if result is WebhookResponse
                if hasattr(result, 'processing_time'):
                    result.processing_time = time.time() - start_time

                return jsonify(result.to_dict()) if hasattr(result, 'to_dict') else result

            except Exception as e:
                if log_errors:
                    print(f"[WEBHOOK_ERROR] {func.__name__}: {e}")

                # Extract query if available in kwargs
                query = kwargs.get('query', '')
                if not query and len(args) > 0:
                    # Try to extract from request data if first arg is request-like
                    try:
                        if hasattr(args[0], 'get_json'):
                            data = args[0].get_json() or {}
                            query = data.get('query', data.get('message', ''))
                    except:
                        pass

                error_response = WebhookResponse(
                    status='error',
                    query=query,
                    answer='',
                    error=str(e),
                    processing_time=time.time() - start_time
                )

                return jsonify(error_response.to_dict()), 500

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                start_time = time.time()
                result = func(*args, **kwargs)

                # Add processing time if result is WebhookResponse
                if hasattr(result, 'processing_time'):
                    result.processing_time = time.time() - start_time

                return jsonify(result.to_dict()) if hasattr(result, 'to_dict') else result

            except Exception as e:
                if log_errors:
                    print(f"[WEBHOOK_ERROR] {func.__name__}: {e}")

                # Extract query if available
                query = kwargs.get('query', '')
                if not query and len(args) > 0:
                    try:
                        if hasattr(args[0], 'get_json'):
                            data = args[0].get_json() or {}
                            query = data.get('query', data.get('message', ''))
                    except:
                        pass

                error_response = WebhookResponse(
                    status='error',
                    query=query,
                    answer='',
                    error=str(e),
                    processing_time=time.time() - start_time
                )

                return jsonify(error_response.to_dict()), 500

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def validate_chat_input(
    require_query: bool = True,
    max_query_length: int = 1000,
    allowed_types: Optional[list] = None
):
    """
    Decorator for validating chat input
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get request data from Flask's global request
            try:
                data = request.get_json() or {}
            except:
                data = kwargs

            # Validate query
            if require_query:
                query = data.get('query', '').strip()
                if not query:
                    error_response = ErrorResponse(
                        error="Query is required",
                        error_type="validation_error"
                    )
                    return jsonify(error_response.to_dict()), 400

                if len(query) > max_query_length:
                    error_response = ErrorResponse(
                        error=f"Query too long (max {max_query_length} characters)",
                        error_type="validation_error"
                    )
                    return jsonify(error_response.to_dict()), 400

            # Validate query types if specified
            if allowed_types:
                query_types = data.get('query_types')
                if query_types and query_types not in allowed_types:
                    error_response = ErrorResponse(
                        error=f"Invalid query_types. Allowed: {allowed_types}",
                        error_type="validation_error"
                    )
                    return jsonify(error_response.to_dict()), 400

            return func(*args, **kwargs)
        return wrapper
    return decorator


def format_chat_response(add_processing_time: bool = True):
    """
    Decorator to ensure response is properly formatted as ChatResponse
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)

            # If result is already a ChatResponse, just add processing time
            if isinstance(result, ChatResponse):
                if add_processing_time:
                    result.processing_time = time.time() - start_time
                return result

            # Convert dict result to ChatResponse
            if isinstance(result, dict):
                # Extract known fields
                answer = result.get('answer', '')
                csv_tables = result.get('csv_tables', [])
                processed_images = result.get('processed_images', [])
                references = result.get('references', [])
                context_used = result.get('context_used', False)

                chat_response = ChatResponse(
                    answer=answer,
                    csv_tables=csv_tables,
                    processed_images=processed_images,
                    references=references,
                    context_used=context_used,
                    processing_time=time.time() - start_time if add_processing_time else None
                )
                return chat_response

            # Fallback for string results
            if isinstance(result, str):
                chat_response = ChatResponse(
                    answer=result,
                    processing_time=time.time() - start_time if add_processing_time else None
                )
                return chat_response

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)

            # Same logic for sync functions
            if isinstance(result, ChatResponse):
                if add_processing_time:
                    result.processing_time = time.time() - start_time
                return result

            if isinstance(result, dict):
                answer = result.get('answer', '')
                csv_tables = result.get('csv_tables', [])
                processed_images = result.get('processed_images', [])
                references = result.get('references', [])
                context_used = result.get('context_used', False)

                chat_response = ChatResponse(
                    answer=answer,
                    csv_tables=csv_tables,
                    processed_images=processed_images,
                    references=references,
                    context_used=context_used,
                    processing_time=time.time() - start_time if add_processing_time else None
                )
                return chat_response

            if isinstance(result, str):
                chat_response = ChatResponse(
                    answer=result,
                    processing_time=time.time() - start_time if add_processing_time else None
                )
                return chat_response

            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def handle_streaming_response(enable_metadata_loading: bool = True):
    """
    Decorator for streaming chat responses with async metadata loading
    Optimized for Flask[async] + Hypercorn
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                # Call the function to get result (could be sync or async)
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                if not isinstance(result, tuple):
                    # Normal response, no streaming
                    return jsonify(result.to_dict() if hasattr(result, 'to_dict') else result)

                # Streaming response: (answer, metadata_task)
                answer, metadata_task = result

                async def generate_stream():
                    """Async generator for streaming with hardcoded optimal values"""
                    stream_id = str(uuid.uuid4())

                    # Hardcoded streaming parameters (optimized for chat UX)
                    CHUNK_SIZE = 25  # Words per chunk
                    DELAY_MS = 0.08  # 80ms delay between chunks

                    # Stream the answer in word chunks
                    words = answer.split()
                    current_chunk = ""
                    chunk_index = 0

                    for i, word in enumerate(words):
                        current_chunk += word + " "

                        # Send chunk when we hit size limit or every few words
                        if (i + 1) % CHUNK_SIZE == 0 or i == len(words) - 1:
                            if current_chunk.strip():
                                chunk_response = StreamingChatResponse(
                                    answer=current_chunk.strip(),
                                    stream_id=stream_id,
                                    is_complete=False,
                                    chunk_index=chunk_index
                                )
                                yield f"data: {chunk_response.to_json()}\\n\\n"
                                chunk_index += 1
                                current_chunk = ""

                                # Async delay for streaming effect
                                await asyncio.sleep(DELAY_MS)

                    # Send completion signal
                    final_response = StreamingChatResponse(
                        answer="",
                        stream_id=stream_id,
                        is_complete=True,
                        chunk_index=chunk_index
                    )
                    yield f"data: {final_response.to_json()}\\n\\n"

                    # If metadata loading enabled, send task info
                    if enable_metadata_loading and metadata_task:
                        metadata_task.stream_id = stream_id
                        payload = {"metadata_task": metadata_task.to_dict()}
                        yield f"data: {json.dumps(payload)}\n\n"

                # Convert async generator to sync for Flask Response
                async def collect_stream():
                    chunks = []
                    async for chunk in generate_stream():
                        chunks.append(chunk)
                    return chunks

                chunks = await collect_stream()

                def sync_generator():
                    for chunk in chunks:
                        yield chunk

                return Response(
                    sync_generator(),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type'
                    }
                )

            except Exception as e:
                error_response = ErrorResponse(
                    error=str(e),
                    error_type="streaming_error",
                    timestamp=time.time()
                )
                return jsonify(error_response.to_dict()), 500

        return async_wrapper
    return decorator


def handle_native_streaming_response(enable_metadata_loading: bool = True):
    """
    Simple native ChatOpenAI streaming - no async complexity!
    Uses synchronous stream() method like: for chunk in llm.stream(messages)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Handle async functions if needed
                if asyncio.iscoroutinefunction(func):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(func(*args, **kwargs))
                    finally:
                        loop.close()
                else:
                    result = func(*args, **kwargs)

                # Non-streaming case
                if not isinstance(result, tuple):
                    payload = result.to_dict() if hasattr(result, 'to_dict') else result
                    return jsonify(payload)

                # Streaming case: (prompt, metadata_task)
                prompt, metadata_task = result

                def generate_streaming_response():
                    """Simple synchronous streaming generator"""
                    stream_id = str(uuid.uuid4())
                    chunk_index = 0
                    
                    try:
                        stream_agent = current_app.stream_agent
                        messages = [
                            SystemMessage(content="Anda adalah sumber informasi Departemen teknik mesin dan Industri UGM (DTMI)."),
                            HumanMessage(content=prompt)
                        ]
                        
                        # Simple synchronous streaming - much cleaner!
                        for chunk in stream_agent.stream(messages):
                            if hasattr(chunk, 'content') and chunk.content:
                                resp = StreamingChatResponse(
                                    answer=chunk.content,
                                    stream_id=stream_id,
                                    is_complete=False,
                                    chunk_index=chunk_index
                                )
                                yield f"data: {resp.to_json()}\n\n"
                                chunk_index += 1

                        # Send completion signal
                        final_resp = StreamingChatResponse(
                            answer="",
                            stream_id=stream_id,
                            is_complete=True,
                            chunk_index=chunk_index
                        )
                        yield f"data: {final_resp.to_json()}\n\n"

                        # Send metadata task info
                        if enable_metadata_loading and metadata_task:
                            payload = {"metadata_task": metadata_task.to_dict()}
                            yield f"data: {json.dumps(payload)}\n\n"

                    except Exception as e:
                        error_resp = StreamingChatResponse(
                            answer=f"Error: {e}",
                            stream_id=stream_id,
                            is_complete=True,
                            chunk_index=chunk_index
                        )
                        yield f"data: {error_resp.to_json()}\n\n"

                return Response(
                    generate_streaming_response(),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type'
                    }
                )

            except Exception as e:
                error_response = ErrorResponse(
                    error=str(e),
                    error_type="native_streaming_error",
                    timestamp=time.time()
                )
                return jsonify(error_response.to_dict()), 500

        return wrapper
    return decorator
