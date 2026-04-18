"""Deterministic stub — no external LLM calls."""

from app.schemas import ProcessMode, ProcessResponse


def generate_structured(text: str, mode: ProcessMode) -> ProcessResponse:
    snippet = text[:160] + ("..." if len(text) > 160 else "")

    if mode == ProcessMode.analyze:
        return ProcessResponse(
            summary=f"[analyze] {snippet}",
            intent="Understand what the user is trying to accomplish.",
            reply="(stub) Consider the analysis above before responding.",
            tasks=["Decide on next steps based on the summary"],
        )

    if mode == ProcessMode.reply:
        return ProcessResponse(
            summary=snippet,
            intent="Produce a helpful reply to the user.",
            reply=f"[reply] Acknowledged: {text[:120]}{'...' if len(text) > 120 else ''}",
            tasks=["Review the draft reply and send when ready"],
        )

    # extract_tasks
    lines = [ln.strip().lstrip("-•").strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        tasks = lines[:10]
    else:
        parts = text.split()
        tasks = [f"Follow up: {w}" for w in parts[:5]] if parts else ["Define one concrete next action"]

    return ProcessResponse(
        summary=snippet,
        intent="Extract actionable tasks from the message.",
        reply="(stub) Tasks listed below.",
        tasks=tasks,
    )
