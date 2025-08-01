from __future__ import annotations
import json
from typing import Literal
from utils.logger import get_logger
from pydantic import BaseModel, Field, ValidationError
from .prompt_instruction import PROMPT_WORKFLOW_INTENT, FEW_SHOT_EXAMPLES


logger = get_logger("workflow_intent")


class IntentRoute(BaseModel):
    intent: Literal["generate_document", "other"]
    confidence_score: float = Field(ge=0, le=1)


# -------- classifier -------------------------------------------
async def classify_intent(llm, query: str, model: str = "gpt-4o") -> IntentRoute:
    """
    Kembalikan IntentRoute; jika model gagal, default => other, score 0.0
    """
    system_msg = PROMPT_WORKFLOW_INTENT()

    # Few-shot sebagai dialog — 4 contoh “golden”
    fewshot = FEW_SHOT_EXAMPLES()

    messages = [
        {"role": "system", "content": system_msg},
        *fewshot,
        {"role": "user", "content": query},
    ]

    try:
        resp = await llm.chat.completions.parse(
            model=model,
            temperature=0,
            top_p=0,
            messages=messages,
            response_format=IntentRoute,
        )
        raw_json = resp.choices[0].message.content
        logger.info(f"Raw router output: {raw_json}")

        return IntentRoute.model_validate_json(raw_json)
    except (ValidationError, json.JSONDecodeError) as ve:
        logger.info(f"Router JSON parse error: {ve}")
    except Exception as e:
        logger.info(f"Router LLM error: {e}")

    # Fallback aman
    return IntentRoute(intent="other", confidence_score=0.0)
