"""
Conversation buffer memory for the LaundryOps Telegram bot.
Stores the last N user/assistant message pairs per chat_id so RAG and NL queries
can use recent context (e.g. follow-up questions: "and what about express?", "same for dry clean?").
In-memory only; resets on bot restart. For production persistence, swap to Redis or Supabase.
"""
from typing import List

# chat_id -> list of {"role": "user" | "assistant", "content": str}
_conversation_buffer: dict[str, list[dict]] = {}

# Keep last N messages (N/2 turns). 20 = 10 user + 10 assistant.
MAX_MESSAGES_PER_CHAT = 20


def get_recent_history(chat_id: str) -> List[dict]:
    """Return the last MAX_MESSAGES_PER_CHAT messages for this chat (oldest first)."""
    buf = _conversation_buffer.get(chat_id) or []
    return list(buf)


def get_formatted_history(chat_id: str, max_turns: int = 5) -> str:
    """
    Return a string suitable for LLM context: "User: ...\\nAssistant: ...\\n..."
    Uses at most the last max_turns exchanges (1 user + 1 assistant = 1 turn).
    """
    buf = get_recent_history(chat_id)
    if not buf:
        return ""
    # Take last (max_turns * 2) messages
    recent = buf[-(max_turns * 2) :] if len(buf) > max_turns * 2 else buf
    lines = []
    for m in recent:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        # Truncate long messages for context window
        if len(content) > 200:
            content = content[:197] + "..."
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def append(chat_id: str, user_message: str, assistant_reply: str) -> None:
    """Append one user message and one assistant reply to this chat's buffer. Trim if over limit."""
    if chat_id not in _conversation_buffer:
        _conversation_buffer[chat_id] = []
    buf = _conversation_buffer[chat_id]
    buf.append({"role": "user", "content": (user_message or "").strip()})
    buf.append({"role": "assistant", "content": (assistant_reply or "").strip()})
    # Trim from left so we keep only the last MAX_MESSAGES_PER_CHAT
    while len(buf) > MAX_MESSAGES_PER_CHAT:
        buf.pop(0)


def clear(chat_id: str) -> None:
    """Clear conversation history for this chat (e.g. after /start if you want a fresh context)."""
    _conversation_buffer.pop(chat_id, None)
