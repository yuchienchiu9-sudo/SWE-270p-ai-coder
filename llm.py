# Name: Yu-Chien Chiu
# Student ID: 56176405
"""
Shared Gemini client used by every agent.

Responsibilities:
- Send a prompt to Gemini and return either a JSON object (generate_json)
  or the plain text of a source file (generate_code).
- Retry on temporary server errors (429/500/503/504), invalid JSON,
  and agent-specific validation failures (e.g. Python SyntaxError).
- Count every API call and its input/output/total tokens, including
  calls that were retried, so the reported usage is honest.
"""

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_ATTEMPTS = 3        # replies that fail parsing/validation
MAX_SERVER_RETRIES = 4  # waits on 429/5xx per request (2, 4, 8, 16 s)
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


def _log(message: str) -> None:
    """Print progress to stderr; stdout is reserved for the MCP stdio protocol."""
    print(f"  [llm] {message}", file=sys.stderr, flush=True)


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


def _call_gemini(prompt: str, json_mode: bool, usage: Usage):
    """
    Send one request, waiting and retrying on temporary server errors
    (429/5xx) up to MAX_SERVER_RETRIES times. Every request is counted.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json" if json_mode else "text/plain"
    )
    for retry in range(MAX_SERVER_RETRIES + 1):
        try:
            response = _get_client().models.generate_content(
                model=MODEL, contents=prompt, config=config
            )
            usage.add(_usage_from_response(response))
            return response
        except errors.APIError as exc:
            usage.api_calls += 1
            if exc.code in RETRYABLE_STATUS and retry < MAX_SERVER_RETRIES:
                wait = 2 ** (retry + 1)
                _log(f"Gemini error {exc.code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise LLMError(f"Gemini API error: {exc}") from exc


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding ```python ... ``` block if Gemini added one."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text + "\n"


def _generate(
    prompt: str,
    json_mode: bool,
    validate: Optional[Callable] = None,
) -> tuple[object, Usage]:
    """
    Shared loop: call Gemini, parse the reply, validate it, and on failure
    re-ask with the error message (up to MAX_ATTEMPTS replies).
    """
    usage = Usage()
    current_prompt = prompt
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = _call_gemini(current_prompt, json_mode, usage)
        try:
            if not response.text:
                raise ValueError("Empty response.")
            if json_mode:
                result = json.loads(response.text)
                if not isinstance(result, dict):
                    raise ValueError("Reply must be a JSON object.")
            else:
                result = _strip_code_fences(response.text)
            if validate is not None:
                validate(result)
            return result, usage
        except (ValueError, SyntaxError) as exc:
            # json.JSONDecodeError is a subclass of ValueError.
            last_error = exc
            _log(f"Invalid reply (attempt {attempt}): {exc}")
            current_prompt = (
                f"{prompt}\n\nYour previous reply was rejected because: {exc}\n"
                "Return a corrected, complete reply that follows all instructions."
            )

    raise LLMError(f"No valid reply after {MAX_ATTEMPTS} attempts: {last_error}")


def generate_json(
    prompt: str,
    validate: Optional[Callable[[dict], None]] = None,
) -> tuple[dict, Usage]:
    """
    Ask Gemini for a JSON object; returns (parsed_object, usage).
    `validate` raises ValueError/SyntaxError if the object is unusable.
    """
    return _generate(prompt, json_mode=True, validate=validate)


def generate_code(
    prompt: str,
    validate: Optional[Callable[[str], None]] = None,
) -> tuple[str, Usage]:
    """
    Ask Gemini for the plain text of one source file; returns (code, usage).
    Plain text avoids the escaping errors that happen when code is put in JSON.
    `validate` raises ValueError/SyntaxError if the code is unusable.
    """
    return _generate(prompt, json_mode=False, validate=validate)


if __name__ == "__main__":
    # Quick self-test: one small JSON request and its token usage.
    data, used = generate_json('Return a JSON object: {"greeting": "Hello"}')
    print("Reply:", data)
    print("Usage:", used.to_dict())
