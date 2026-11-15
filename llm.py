# Name: Yu-Chien Chiu
# Student ID: 56176405
"""
Shared Gemini client used by every agent.

Responsibilities:
- Send a prompt to Gemini and parse the JSON reply.
- Retry on temporary server errors (429/500/503/504), invalid JSON,
  and agent-specific validation failures (e.g. Python SyntaxError).
- Count every API call and its input/output/total tokens, including
  calls that were retried, so the reported usage is honest.
"""

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 503, 504}
TIMEOUT_MS = 120_000

_client: Optional[genai.Client] = None


class LLMError(RuntimeError):
    """Raised when Gemini cannot produce a valid reply after all retries."""


@dataclass
class Usage:
    """LLM usage counters: number of API calls and tokens used."""

    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "Usage") -> None:
        """Add another Usage object's counts into this one."""
        self.api_calls += other.api_calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens

    def to_dict(self) -> dict:
        """Return the counters as a plain dict (JSON-serializable)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Usage":
        """Build a Usage object from a dict produced by to_dict()."""
        return cls(**{k: int(data.get(k, 0)) for k in cls.__dataclass_fields__})


def _get_client() -> genai.Client:
    """Create the Gemini client on first use, reading GEMINI_API_KEY from .env."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("GEMINI_API_KEY is missing. Add it to the .env file.")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
    return _client


def _usage_from_response(response) -> Usage:
    """Extract token counts from one Gemini response (thinking tokens count as output)."""
    meta = response.usage_metadata
    if meta is None:
        return Usage(api_calls=1)
    output = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
    return Usage(
        api_calls=1,
        input_tokens=meta.prompt_token_count or 0,
        output_tokens=output,
        total_tokens=meta.total_token_count or 0,
    )


def generate_json(
    prompt: str,
    validate: Optional[Callable[[dict], None]] = None,
) -> tuple[dict, Usage]:
    """
    Ask Gemini for a JSON object and return (parsed_object, usage).

    `validate` is an optional function that raises ValueError or SyntaxError
    if the reply is unusable; the error message is sent back to Gemini on the
    next attempt so it can correct itself.
    """
    usage = Usage()
    current_prompt = prompt
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # 1. Call Gemini, retrying temporary server errors with backoff.
        try:
            response = _get_client().models.generate_content(
                model=MODEL,
                contents=current_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
        except errors.APIError as exc:
            usage.api_calls += 1
            last_error = exc
            if exc.code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                wait = 2 ** attempt
                print(f"  Gemini error {exc.code}, retrying in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            raise LLMError(f"Gemini API error: {exc}") from exc

        usage.add(_usage_from_response(response))

        # 2. Parse and validate the reply; on failure, ask Gemini to fix it.
        try:
            if not response.text:
                raise ValueError("Empty response.")
            data = json.loads(response.text)
            if not isinstance(data, dict):
                raise ValueError("Reply must be a JSON object.")
            if validate is not None:
                validate(data)
            return data, usage
        except (ValueError, SyntaxError) as exc:
            # json.JSONDecodeError is a subclass of ValueError.
            last_error = exc
            print(f"  Invalid reply (attempt {attempt}): {exc}", flush=True)
            current_prompt = (
                f"{prompt}\n\nYour previous reply was rejected because: {exc}\n"
                "Return a corrected, complete reply that follows all instructions."
            )

    raise LLMError(f"No valid reply after {MAX_ATTEMPTS} attempts: {last_error}")


if __name__ == "__main__":
    # Quick self-test: one small JSON request and its token usage.
    data, used = generate_json('Return a JSON object: {"greeting": "Hello"}')
    print("Reply:", data)
    print("Usage:", used.to_dict())
