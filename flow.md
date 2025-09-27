# Query Endpoint Flow Documentation

## Overview
The `/api/query` endpoint is the main SSE streaming endpoint that handles user queries through a context-aware routing system with RAG capabilities.

## High-Level Architecture

```
User Query → Validation → Router Decision → Action Flow → Response Stream
```

## Detailed Flow

### 1. Request Validation
**File**: `stream_query.py:73-84`
```
ValidationService.validate_api_request()
↓
Extract: query, query_types, year, top_k, context_expansion_window
```

### 2. Service Initialization
**File**: `stream_query.py:108-120`
```
RouterAgent(llm, DTMI_DOMAIN)
FilterService(vectorstore, llm, context_expansion_window, max_workers=13)
StreamHandler(stream_agent)
MetadataService()
PromptService(DTMI_DOMAIN)
```

### 3. Context Retrieval
**File**: `stream_query.py:124`
```
get_msg_hist(session_id)
↓
InMemoryHistory.get_history(session_id)
↓
Returns: ["Human: clean_query", "AI: response", ...]
```

**History Processing**:
- Human messages: Extracted from `$query$` format → clean query only
- AI messages: Stored as-is (full responses/clarifications)
- Returns last N exchanges for context

### 4. Router Decision
**File**: `router_service.py:10`
```
RouterAgent.get_action(query, conversation_history)
↓
Analyzes: conversation context + current query
↓
Returns: 2 possible actions
```

**Router Actions**:

#### A. RAG Action
```json
{
  "action": "rag",
  "expanded_query": "Full contextual question",
  "rag_optimized_query": "keywords for vector search"
}
```

#### B. No-RAG Action  
```json
{
  "action": "no_rag",
  "response": "Direct response or clarification",
  "what_to_clarify": "type" | null
}
```

### 5. Action Flow Branches

## 5A. No-RAG Flow
**File**: `stream_query.py:151-174`

### Current Implementation (BROKEN):
```
no_rag action
↓
Store original query in history
↓
PromptService.build_no_rag_prompt(response) → returns response as-is
↓
StreamHandler.stream_from_prompt(response) → sends to LLM
↓
LLM processes response → streams back
```

### Problem:
- **Clarifications sent to LLM**: Router's clarification question gets processed by LLM instead of sent directly to user
- **Unnecessary LLM call**: Direct responses should sometimes bypass LLM entirely

### Should Be:
```
if what_to_clarify present:
    Send clarification directly to user (no LLM)
else:
    Send to LLM for direct response processing
```

## 5B. RAG Flow  
**File**: `stream_query.py:177-267`

```
rag action
↓
FilterService.get_rag(
    query=rag_optimized_query,           # Keywords for vector search
    relevance_query=expanded_query        # Full question for relevance
)
↓
PromptService.build_rag_prompt(
    query=expanded_query,                # Full question  
    retrieved_content=context
)
↓
Result: "Query: $expanded_query$" with RAG context
↓
Store original query in history
↓
StreamHandler.stream_from_prompt(rag_prompt)
↓
LLM processes → streams response
↓
MetadataService processes images/tables in background
```

## 6. Response Streaming
**SSE Format**:
```
data: {"type":"stream_start"}
data: {"type":"chunk","data":"response chunk"}
data: {"type":"metadata","data":{...}}
data: {"type":"status","message":"..."}
data: {"type":"stream_end"}
```

## 7. History Management

### Chat History Flow:
```
User Input → Router → Prompt Building → History Storage
```

**Storage Logic**:
- **RAG prompts**: `"Query: $expanded_query$"` → stores `expanded_query` only
- **No-RAG prompts**: `"clarification text"` → stores full text as-is  
- **System messages**: Always preserved at position 0
- **Trimming**: Keeps system + last N human-AI exchange pairs

## Current Issues & Fixes Needed

### 1. No-RAG Pipeline Issue
**Problem**: Clarifications are sent to LLM instead of directly to user

**Fix**: 
```python
if router_result.get('what_to_clarify'):
    # Send clarification directly (no LLM processing)
    yield clarification_chunks_directly
else:
    # Process through LLM for direct responses
    stream_from_prompt(no_rag_response)
```

### 2. Service Responsibility Violations
**Current**: stream_query.py mixes prompt building logic
**Fixed**: All prompt building delegated to PromptService

### 3. Context Expansion Window
**Usage**: Controls how many surrounding chunks to include in RAG retrieval
**Default**: Set in validation, passed to FilterService

## Service Responsibilities (SOC)

### RouterService
- **Single Responsibility**: Routing decisions based on context
- **Input**: Query + conversation history  
- **Output**: Structured decision data

### PromptService  
- **Single Responsibility**: Building prompts for different scenarios
- **Methods**: `build_rag_prompt()`, `build_no_rag_prompt()`, `build_raw_prompt()`

### FilterService
- **Single Responsibility**: RAG retrieval and filtering
- **Input**: Optimized query + filters
- **Output**: Retrieved context + metadata

### StreamHandler
- **Single Responsibility**: LLM streaming interface
- **Input**: Final prompt
- **Output**: Streamed response chunks

### MetadataService
- **Single Responsibility**: Background processing of images/tables
- **Async**: Processes while response streams

## Configuration

### Environment Variables
- `MEMORY_EXCHANGES`: Number of conversation exchanges to remember (default: 1)
- `OPENAI_API_KEY`, `OPENAI_MODEL`: LLM configuration
- `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION_NAME`: Vector DB config

### Request Parameters
- `query`: User question (required)
- `query_types`: Filter types ["text", "image", "table"] or "all"
- `year`: Document year filter ("2024", "2025", null)
- `top_k`: Number of results to retrieve
- `context_expansion_window`: Surrounding context chunks to include

## Debug Output
All services provide debug logging:
- `[ROUTER DEBUG]`: Router decisions and reasoning
- `[CONTEXT DEBUG]`: Conversation history analysis  
- `[RAG ERROR]`: Vector search failures
- `[CLEANUP ERROR]`: Async cleanup issues

## Session Management
- **Session ID**: Generated from IP + User-Agent hash
- **History Expiry**: 2 minutes of inactivity
- **Background Cleanup**: Removes expired sessions automatically