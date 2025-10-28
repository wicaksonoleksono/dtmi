# Token Usage Optimization Analysis

## 🔍 Complete Flow Trace

### Request Flow:
```
User Query
  ↓
stream_query.py::query()
  ↓
generate_stream()
  ↓
┌─────────────────────────────────────────────┐
│ 1. RouterAgent.get_action()                │ ← LLM Call #1 (Router)
│    - Analyzes query                         │
│    - Decides: RAG or No-RAG                 │
└─────────────────────────────────────────────┘
  ↓
┌─────────────── IF RAG PATH ─────────────────┐
│ 2. FilterService.get_rag()                  │
│    ├─ similarity_search (top_k docs)        │
│    ├─ expand_text (context window)          │
│    └─ evaluate_relevance()                  │ ← LLM Calls #2-#N (per doc!)
│       └─ __batch_relevance_check()          │   **MAJOR COST HERE**
│          └─ LLM call per document           │
│                                              │
│ 3. PromptService.build_rag_prompt()         │
│    - Combines RAG context + query           │
└──────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────┐
│ 4. StreamHandler.stream_from_prompt()       │ ← LLM Call #Final (Streaming)
│    - Full conversation history              │
│    - System prompt                          │
│    - RAG context (if applicable)            │
│    - Streams response                       │
└─────────────────────────────────────────────┘
```

---

## 💰 Token Cost Breakdown

### INPUT TOKENS (What You Pay For):

#### 1. **Router LLM Call** (`router_service.py:117`)
**Estimated: ~1,200-1,500 tokens per request**

```python
# Components:
- DTMI_DOMAIN context: ~300 tokens
- Router instructions + examples: ~600 tokens
- Previous conversation: N messages * ~50-150 tokens each
- Current query: ~20-100 tokens
```

**File**: `router_service.py:39-115`

---

#### 2. **Relevance Check LLM Calls** (`filter_service.py:282-332`)
**Estimated: ~6,000-10,000 tokens per request** ⚠️ **MOST EXPENSIVE**

```python
# PER DOCUMENT (runs for top_k=20 docs):
- Document content: ~200-500 tokens each
- Relevance prompt: ~200 tokens
- Query: ~20-100 tokens

# TOTAL: 20 documents × ~400 tokens = ~8,000 tokens
# This is 20 separate LLM API calls!
```

**File**: `filter_service.py:282-332`

**Problem**: Line 359 runs `await asyncio.gather(*[eval_one(doc, score) for doc, score in uncached])`
- This spawns 10-20 parallel LLM calls
- Each with full document content
- No batching strategy

---

#### 3. **Final Streaming Call** (`stream_handler.py:34`)
**Estimated: ~2,000-8,000 tokens per request**

```python
# Components:
- System prompt: ~400 tokens (__init__.py:58-82)
- Conversation history: MEMORY_EXCHANGES * 2 * ~100 tokens
- RAG context: ~1,000-5,000 tokens (can be HUGE!)
  └─ Combined from filter_service.py:515
     └─ Includes FULL CSV tables!
- User query: ~20-100 tokens
```

**File**: `stream_handler.py:34` + `__init__.py:119-122`

---

### OUTPUT TOKENS (What You Pay For):

```
Router response:        ~50-100 tokens
Relevance checks:       ~30 tokens × 20 docs = ~600 tokens
Final response:         ~200-1,000 tokens
```

---

## 🔥 Critical Optimization Opportunities

### **Priority 1: ELIMINATE/REDUCE Relevance Checking** ⚠️ **SAVES 70-80% OF COSTS**

**Current Issue**: `filter_service.py:282-361`
- Running **20 separate LLM calls** to check if each document is relevant
- Each call includes full document content (~400 tokens)
- **Total**: ~8,000 input tokens + ~600 output tokens per request
- **This is your biggest cost!**

#### **Solutions**:

**Option A: Use Similarity Score Threshold (Best - No LLM calls)**
```python
# filter_service.py:496
# BEFORE:
relevant_docs = await self.evaluate_relevance(all_docs, relevance_query) if all_docs else []

# AFTER:
SIMILARITY_THRESHOLD = 0.3  # Tune based on your data
relevant_docs = [(doc, score) for doc, score in all_docs if score < SIMILARITY_THRESHOLD]
# Note: Lower score = more similar in many vector DBs
```
**Savings**: ~8,600 tokens per request (removes 20 LLM calls!)

**Option B: Batch Relevance Checking (Reduces to 1-2 LLM calls)**
```python
# filter_service.py:282-332
# Instead of checking each doc separately, batch them:

async def __batch_relevance_check_v2(self, docs: List[Document], query: str) -> List[bool]:
    """Check relevance for multiple docs in ONE LLM call"""

    # Combine all docs into one prompt
    docs_text = "\n\n".join([
        f"Document {i+1}:\n{doc.page_content[:300]}..."  # Truncate!
        for i, doc in enumerate(docs[:10])  # Process in batches of 10
    ])

    prompt = f"""
    Query: {query}

    Documents:
    {docs_text}

    Return JSON array of true/false for each document's relevance:
    ["explanation for doc 1", "explanation for doc 2", ...]
    """

    # Single LLM call for 10 docs instead of 10 separate calls
    response = await self.llm.ainvoke([HumanMessage(content=prompt)])
    # Parse and return results
```
**Savings**: ~7,000 tokens per request (20 calls → 2 calls)

**Option C: Remove Relevance Checking Entirely**
- Trust the vector similarity search
- The embedding model already does relevance matching
- Add post-processing filters if needed (keyword matching, metadata filtering)

---

### **Priority 2: Compress Router Prompt** 💡 **SAVES ~500 tokens**

**Current Issue**: `router_service.py:39-115`
- Very verbose with many examples
- Repeated instructions
- Long domain context

#### **Solution: Compress Router Prompt**
```python
# router_service.py:39-115
# Current: ~900 tokens
# Target: ~400 tokens (save ~500 tokens)

# BEFORE: 900 tokens
router_prompt = f"""
Kamu adalah RouterAgent dengan 2 aksi sederhana:
Domain:
{self.dtmi_domain}  # This alone is ~300 tokens!
{context_section}
Query Saat Ini: "{query}"
... (many examples and verbose rules) ...
"""

# AFTER: ~400 tokens
router_prompt = f"""
Task: Decide if query needs RAG search.

Domain: DTMI UGM (Teknik Mesin & Industri) - mata kuliah, dosen, kurikulum, persyaratan
{context_section if previous_conversation else ""}
Query: "{query}"

Output JSON:
- action: "rag" (needs specific DTMI data) or "no_rag" (greeting/general/clarification)
- For RAG: expanded_query (full question), rag_optimized_query (keywords only, no stopwords)
- For no_rag: what_to_clarify (if ambiguous, else null)

Rules:
- rag_optimized_query: remove "berapa/siapa/kapan/bagaimana", keep "SKS/IPK/dosen"
- Expand abbreviations: TI→Teknik Industri, TM→Teknik Mesin, matkul→mata kuliah
- Clarify if: ambiguous terms, missing context, incomplete question

JSON only, no markdown.
"""
```

**Savings**: ~500 tokens per request

---

### **Priority 3: Limit RAG Context Size** 💡 **SAVES ~2,000-4,000 tokens**

**Current Issue**: `filter_service.py:206-277` + `filter_service.py:515`
- Including FULL CSV tables in context
- No truncation of long documents
- No maximum context length

#### **Solution A: Truncate Large Content**
```python
# filter_service.py:510
# Add max_context_chars parameter

async def __batch_build_content(self, docs: List[Document],
                                 include_full_table: bool = True,
                                 max_content_chars: int = 4000) -> List[str]:  # NEW
    csv_md_map = await self.__batch_load_csv(docs)
    total_chars = 0
    results = []

    for doc in docs:
        content = one(doc)  # Your existing logic

        # Truncate if needed
        if total_chars + len(content) > max_content_chars:
            remaining = max_context_chars - total_chars
            if remaining > 100:  # Only add if meaningful space left
                content = content[:remaining] + "... [truncated]"
                results.append(content)
            break

        total_chars += len(content)
        results.append(content)

    return results
```

#### **Solution B: Summarize Long Tables**
```python
# filter_service.py:234-270
# For tables, include preview instead of full content:

if include_full_table:
    # BEFORE: Full table
    content += f"\nFull Table: {caption}\n{md_table}"

    # AFTER: Smart preview
    if len(md_table) > 500:
        # Show first 5 rows + last 2 rows
        lines = md_table.split('\n')
        preview = '\n'.join(lines[:7] + ['...', '(table truncated)'] + lines[-2:])
        content += f"\nTable Preview: {caption}\n{preview}\nTotal rows: {len(lines)-2}"
    else:
        content += f"\nTable: {caption}\n{md_table}"
```

**Savings**: ~2,000-4,000 tokens per request

---

### **Priority 4: Optimize Conversation History** 💡 **SAVES ~500-1,000 tokens**

**Current Issue**: `__init__.py:26` + `stream_query.py:18-40`
- No token counting for history
- `MEMORY_EXCHANGES = 1` but no enforcement of token limits
- Long messages accumulate

#### **Solution: Token-Aware History Trimming**
```python
# chat_history.py (modify get_history)

from tiktoken import get_encoding

class InMemoryHistory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages = []
        self.max_tokens = 1000  # NEW: Token budget for history
        self.encoder = get_encoding("cl100k_base")  # GPT-4 tokenizer

    def add_messages(self, messages):
        self.messages.extend(messages)
        self._trim_to_token_budget()  # NEW

    def _trim_to_token_budget(self):
        """Keep only recent messages that fit in token budget"""
        total_tokens = 0
        keep_messages = []

        # Count backwards (keep recent messages)
        for msg in reversed(self.messages):
            msg_tokens = len(self.encoder.encode(msg.content))
            if total_tokens + msg_tokens > self.max_tokens:
                break
            keep_messages.insert(0, msg)
            total_tokens += msg_tokens

        self.messages = keep_messages
```

**Savings**: ~500-1,000 tokens per request

---

### **Priority 5: Compress System Prompts** 💡 **SAVES ~200-300 tokens**

**Current Issue**: `__init__.py:58-82`
- Verbose system prompt
- Repeated instructions

#### **Solution**:
```python
# __init__.py:58-82
# Current: ~400 tokens
# Target: ~200 tokens

# BEFORE:
STREAM_SYSTEM_PREPROMPT = SystemMessage(content="""
Kamu adalah **Tasya** alias Tanya Saya  asisten milik DTMI UGM
DTMI singkatan dari Departemen Teknik mesin dan Industri
TI adalah Teknik Industri TM adalah Teknik Mesin
Kamu digunakan Untuk Membantu dosen maupun mahasiswa...
(400+ tokens of instructions)
""")

# AFTER:
STREAM_SYSTEM_PREPROMPT = SystemMessage(content="""
Tasya - Asisten DTMI UGM (Departemen Teknik Mesin & Industri)

Tugas: Jawab pertanyaan DTMI dengan RAG context
Rules:
1. Jangan politik/SARA → arahkan ke DTMI
2. Tangani basa-basi natural
3. Gunakan konteks percakapan
4. Jawab informatif, list jika bisa
5. Jika no context: "Mohon maaf, data tidak ditemukan. Silakan hubungi administrasi DTMI UGM 🙏"
""")
```

**Savings**: ~200 tokens per request

---

## 💸 Total Potential Savings

### Current Token Usage (per request):
```
Router LLM:              ~1,200 tokens (input)
Relevance checks:        ~8,600 tokens (input + output) ⚠️
Final stream:            ~4,000 tokens (input)
TOTAL INPUT:            ~13,800 tokens
TOTAL OUTPUT:           ~800 tokens
───────────────────────────────────────
TOTAL PER REQUEST:      ~14,600 tokens
```

### After Optimizations:
```
Router LLM (compressed):     ~700 tokens (input)
Relevance (removed):           ~0 tokens ✅
Final stream (optimized):  ~2,000 tokens (input)
TOTAL INPUT:               ~2,700 tokens
TOTAL OUTPUT:                ~800 tokens
───────────────────────────────────────
TOTAL PER REQUEST:         ~3,500 tokens
```

### **Savings: ~11,100 tokens per request (76% reduction!)**

---

## 🎯 Implementation Priority

### **URGENT (Do First)**:
1. **Remove/Replace Relevance Checking** (`filter_service.py:282-361`)
   - Savings: ~8,600 tokens (60% of total cost)
   - Effort: Medium (2-3 hours)
   - Risk: Low (trust vector similarity)

### **HIGH PRIORITY**:
2. **Compress Router Prompt** (`router_service.py:39-115`)
   - Savings: ~500 tokens
   - Effort: Low (30 mins)
   - Risk: Low (test with examples)

3. **Limit RAG Context Size** (`filter_service.py:510`)
   - Savings: ~2,000-4,000 tokens
   - Effort: Medium (2 hours)
   - Risk: Medium (ensure quality maintained)

### **MEDIUM PRIORITY**:
4. **Token-Aware History** (`chat_history.py`)
   - Savings: ~500-1,000 tokens
   - Effort: Medium (3 hours)
   - Risk: Low

5. **Compress System Prompts** (`__init__.py:58-82`)
   - Savings: ~200 tokens
   - Effort: Low (15 mins)
   - Risk: Low

---

## 📊 Cost Impact (Assuming GPT-4o Pricing)

### Current Costs (per 1000 requests):
```
Input:  13,800 tokens × 1000 × $0.0025/1K  = $34.50
Output:    800 tokens × 1000 × $0.010/1K   = $8.00
                                    TOTAL  = $42.50
```

### After Optimizations (per 1000 requests):
```
Input:  2,700 tokens × 1000 × $0.0025/1K  = $6.75
Output:   800 tokens × 1000 × $0.010/1K   = $8.00
                                   TOTAL  = $14.75
```

### **Savings: $27.75 per 1000 requests (65% cost reduction)**

If you process 10,000 requests/day:
- **Before**: $425/day = $12,750/month
- **After**: $147.50/day = $4,425/month
- **Savings**: $277.50/day = **$8,325/month**

---

## 🔧 Quick Wins (Do Today)

### 1. Disable Relevance Checking (5 mins):
```python
# filter_service.py:496
# Comment out this line:
# relevant_docs = await self.evaluate_relevance(all_docs, relevance_query) if all_docs else []

# Replace with:
relevant_docs = all_docs  # Trust vector similarity
```

### 2. Add Context Size Limit (10 mins):
```python
# filter_service.py:515
combined_context = "\n\n".join(all_texts)

# Add max length:
MAX_CONTEXT_CHARS = 4000
if len(combined_context) > MAX_CONTEXT_CHARS:
    combined_context = combined_context[:MAX_CONTEXT_CHARS] + "\n... [context truncated]"
```

### 3. Compress System Prompt (5 mins):
```python
# __init__.py:58-82
# Replace with shorter version (see Priority 5 above)
```

**Total time: 20 minutes**
**Immediate savings: ~10,000 tokens per request (68% reduction)**

---

## 📝 Testing Strategy

After each optimization:

1. **A/B Test**:
   - Keep old code path
   - Route 10% traffic to optimized version
   - Compare response quality

2. **Metrics to Track**:
   - Tokens used (input/output)
   - Response quality score
   - Response time
   - Cost per request

3. **Rollback Plan**:
   - Keep feature flag
   - Monitor for 24 hours
   - Revert if quality drops > 5%

---

## 🚨 Warnings

1. **Removing Relevance Checking**:
   - May include slightly less relevant results
   - But vector similarity is usually good enough
   - Test with your queries first

2. **Truncating Context**:
   - May cut off important information
   - Use smart truncation (keep first + last parts)
   - Monitor "data not found" responses

3. **Compressing Prompts**:
   - LLM may be less reliable
   - Test edge cases thoroughly
   - Keep examples for critical logic

---

## 📚 Files to Modify

```
Priority 1 (Relevance):
  - flask_app/app/service/filter_service.py:282-361

Priority 2 (Router):
  - flask_app/app/service/router_service.py:39-115

Priority 3 (Context):
  - flask_app/app/service/filter_service.py:206-277
  - flask_app/app/service/filter_service.py:510-515

Priority 4 (History):
  - flask_app/app/service/chat_history.py

Priority 5 (System Prompt):
  - flask_app/app/__init__.py:58-82
```

---

## 🎉 Summary

**The #1 thing costing you money**: Relevance checking with 20 separate LLM calls per request.

**Quick fix** (20 mins):
1. Remove relevance checking
2. Add context size limit
3. Compress system prompt

**Result**: 68% cost reduction immediately, with minimal risk.

**Full optimization** (1-2 days):
- 76% token reduction
- 65% cost savings
- $8,325/month saved (at 10K requests/day)
