from __future__ import annotations

from .reasoning_logger import log_reasoning_step
from services.llm_provider import chat_complete


async def respond_as_assistant(message: str, workflow_id: str | None = None) -> dict:
    prompt = (
        "Answer as a supply-chain workflow assistant. "
        "Explain what analyses are available and answer the user's question directly when possible.\n\n"
        f"User message:\n{message.strip()}"
    )
    try:
        text, used = await chat_complete(prompt, system="", max_tokens=500, workflow_id=workflow_id, agent_name="assistant_agent")
    except Exception:
        used = "local"
        text = (
            "I can help with schedule analysis, political risk, tariff risk, logistics risk, "
            "and consolidated reporting. Ask for a specific risk type or request a full risk report."
        )

    if workflow_id:
        log_reasoning_step(
            workflow_id,
            "assistant_agent",
            "general_response",
            f"Prepared a general assistant response using provider {used}.",
            "success",
            {"provider": used},
        )
    return {"provider": used, "text": text.strip()}
