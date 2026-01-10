import asyncio
from typing import AsyncGenerator
from flask import g


class StreamHandler:
    """
    """

    def __init__(self, stream_agent):
        self.stream_agent = stream_agent

    async def stream_from_prompt(
        self, final_prompt: str, session_id: str = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM response from a prepared prompt with session history.
        Yields raw string chunks for SSE.
        """
        # 1) Use provided session_id or try to get from Flask g (for backward compatibility)
        if session_id is None:
            try:
                session_id = getattr(g, "session_id", None)
            except RuntimeError:
                # Not in Flask context - use default session
                session_id = "test-session"

        if not session_id:
            session_id = "default-session"
        llm_config = {"configurable": {"session_id": session_id}}
        accumulated = ""
        idx = 0
        try:
            async for msg in self.stream_agent.astream(final_prompt, config=llm_config):
                chunk = getattr(msg, "content", str(msg))
                if not chunk:
                    continue

                accumulated += chunk
                yield chunk
                idx += 1

        except Exception as e:
            yield f"[stream error] {e}"
            return

    async def get_complete_response(self, final_prompt: str, session_id: str = None) -> str:
        """
        Non‐streaming path for when you just want the full reply.
        """
        # Use provided session_id or try to get from Flask g (for backward compatibility)
        if session_id is None:
            try:
                session_id = getattr(g, "session_id", None) or ""
            except RuntimeError:
                # Not in Flask context - use default session
                session_id = "test-session"

        resp = await self.stream_agent.ainvoke(
            final_prompt,
            config={"configurable": {"session_id": session_id}}
        )
        return getattr(resp, "content", str(resp))
