import re
import time
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, BaseMessage
from pydantic import BaseModel, Field
from typing import Dict, List, Type
from flask import current_app
import threading


class InMemoryHistory(BaseChatMessageHistory, BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    system_initialized: bool = Field(default=False)

    class Config:
        arbitrary_types_allowed = True

    def add_messages(self, messages: List[BaseMessage]) -> None:
        # Process each message to clean HumanMessage content while preserving AI messages
        processed_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                # original_content = msg.content
                cleaned_content = self._extract_query_from_human_message(msg.content)
                processed_messages.append(HumanMessage(content=cleaned_content))
            else:
                processed_messages.append(msg)
                
        self.messages.extend(processed_messages)
        # Trim after every write
        self._trim_to_last_n_exchanges()
        
    def clear(self) -> None:
        self.messages = []
        self.system_initialized = False

    def ensure_system_message(self) -> None:
        """Add system message at the start if not already added."""
        if not self.system_initialized and hasattr(current_app, "config"):
            system_prompt = current_app.config.get("STREAM_SYSTEM_PROMPT")
            if system_prompt:
                self.messages.insert(0, SystemMessage(content=system_prompt))
                self.system_initialized = True

    def _extract_query_from_human_message(self, content: str) -> str:
        """
        Extract the original query from the HumanMessage content if it's in the format ${query}$.
        If the format is not found, return the original content.
        """
        # Look for the pattern ${...}$ (query wrapped with $)
        # Note: We're looking for the specific format used in build_rag_prompt: Query: ${query}$
        pattern = r"\$(.*?)\$"
        match = re.search(pattern, content)
        if match:
            # Return just the query part extracted from the ${query}$ format
            return match.group(1).strip()
        else:
            # If the pattern isn't found, return the original content
            return content

    # --- trimming helpers ---
    def _trim_to_last_n_exchanges(self) -> None:
        """
        Keep the system prompt (if any) + the last N (human, ai) exchanges.
        N is read from FLASK config: MEMORY_EXCHANGES (default=1).
        """
        n = 1
        if hasattr(current_app, "config"):
            n = int(current_app.config.get("MEMORY_EXCHANGES", 1))

        if not self.messages:
            return

        # Peel off leading system message if present
        sys_msgs = []
        rest = self.messages
        if self.system_initialized and isinstance(self.messages[0], SystemMessage):
            sys_msgs = [self.messages[0]]
            rest = self.messages[1:]

        # Walk from the end, collect last n Human+AI pairs (in order)
        kept: List[BaseMessage] = []
        human_count = 0
        ai_count = 0
        pairs_collected = 0

        # We want complete exchanges; scan backward and rebuild
        temp: List[BaseMessage] = []
        for m in reversed(rest):
            temp.append(m)
            # Count roles to find pairs in reverse
            if isinstance(m, HumanMessage):
                human_count += 1
            elif isinstance(m, AIMessage):
                ai_count += 1

            # When we've seen at least one Human and one AI since last cut, that's one exchange
            if human_count >= 1 and ai_count >= 1:
                pairs_collected += 1
                human_count = 0
                ai_count = 0
                if pairs_collected == n:
                    break

        # temp currently holds tail slice in reverse; fix order
        tail = list(reversed(temp))

        # If the very end doesn't close an exchange (e.g., only a Human so far),
        # keep it too so the model sees the latest prompt.
        # (Optional: comment this out if you want strictly completed exchanges only.)
        # No-op here because `tail` already includes th danglieng message.

        self.messages = sys_msgs + tail


# Global store keyed by session_id with access time tracking
# Format: {session_id: (history_instance, last_access_time)}
_store: Dict[str, tuple] = {}
_EXPIRY_TIME = 120  # 2 minutes in seconds
_MAX_SESSIONS = 100  # Hard limit to prevent memory blow
_cleanup_lock = threading.Lock()
_cleanup_thread = None
_cleanup_thread_running = threading.Event()


def _cleanup_expired_sessions():
    """Efficient cleanup with memory protection"""
    current_time = time.time()
    expired_sessions = []
    
    with _cleanup_lock:
        # If we're at max capacity, force cleanup of oldest sessions
        if len(_store) >= _MAX_SESSIONS:
            # Sort by last_access and remove oldest 20%
            sorted_sessions = sorted(_store.items(), key=lambda x: x[1][1])
            sessions_to_remove = sorted_sessions[:_MAX_SESSIONS // 5]
            for session_id, _ in sessions_to_remove:
                expired_sessions.append(session_id)
        else:
            # Normal time-based cleanup
            for session_id, (history, last_access) in _store.items():
                if current_time - last_access > _EXPIRY_TIME:
                    expired_sessions.append(session_id)
        
        # Remove in batches to avoid long locks
        for session_id in expired_sessions:
            if session_id in _store:
                del _store[session_id]
    
    if expired_sessions:
        print(f"Cleaned up {len(expired_sessions)} sessions")


def _background_cleanup():
    """Dynamic interval cleanup based on load"""
    while not _cleanup_thread_running.is_set():
        try:
            user_count = len(_store)
            
            # Dynamic interval: more load = more frequent cleanup
            if user_count > 80:
                interval = 10
            elif user_count > 50:
                interval = 15
            else:
                interval = 30
                
            if _cleanup_thread_running.wait(interval):
                break  # Exit if the event is set (cleanup requested)
            _cleanup_expired_sessions()
        except Exception as e:
            print(f"Error in background cleanup: {e}")


def _ensure_background_cleanup():
    """Ensure the background cleanup thread is running"""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_thread_running.clear()
        _cleanup_thread = threading.Thread(target=_background_cleanup, daemon=True)
        _cleanup_thread.start()


def get_history(session_id: str) -> BaseChatMessageHistory:
    """Get chat history for a session, constrained to last N exchanges."""
    # Ensure the background cleanup thread is running
    _ensure_background_cleanup()
    
    current_time = time.time()
    
    # Perform cleanup of expired sessions periodically (every access)
    # This ensures we don't accumulate too many expired sessions in memory
    if len(_store) > 0:  # Only cleanup if there are sessions to check
        _cleanup_expired_sessions()
    
    if session_id not in _store:
        # Create new history with current time
        _store[session_id] = (InMemoryHistory(), current_time)
    else:
        # Update the access time for existing session
        history, _ = _store[session_id]
        _store[session_id] = (history, current_time)
    
    history, _ = _store[session_id]
    history.ensure_system_message()
    # Defensive: re-trim on access in case config changed mid-run
    history._trim_to_last_n_exchanges()
    return history


def cleanup_all_histories():
    """Function to clean up all histories and stop the background thread"""
    global _cleanup_thread
    _cleanup_thread_running.set()
    if _cleanup_thread:
        _cleanup_thread.join(timeout=1)  # Wait up to 1 second for thread to finish
    _store.clear()
