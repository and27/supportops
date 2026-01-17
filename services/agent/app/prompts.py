from __future__ import annotations

import os

DEFAULT_CLARIFY_PROMPT = (
    "Can you add more context (account, steps, and expected behavior)?"
)
ECOMMERCE_CLARIFY_PROMPT = (
    "What product or service do you want, which city are you in, and what is your "
    "payment method or order number?"
)


def get_clarify_prompt() -> str:
    override = os.getenv("CLARIFY_PROMPT", "").strip()
    if override:
        return override
    mode = os.getenv("CLARIFY_PROMPT_MODE", "default").strip().lower()
    if mode == "ecommerce":
        prompt = os.getenv("CLARIFY_PROMPT_ECOMMERCE", "").strip()
        return prompt or ECOMMERCE_CLARIFY_PROMPT
    return DEFAULT_CLARIFY_PROMPT
