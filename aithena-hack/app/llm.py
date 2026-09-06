# app/llm.py
# Uses SYNCHRONOUS httpx wrapped in asyncio.to_thread to avoid
# Python 3.14 async cancellation bugs with httpx.
import httpx
import json
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-4"

# ONE global limit on simultaneous outbound requests, for the WHOLE app.
#
# Before this: each agent had its OWN semaphore (extract.py, agent_retrieval.py,
# agent_refuter.py), uncoordinated with each other. Agents 2/3/4 also run
# concurrently WITH each other per document, so worst case was 3+3+1=7
# simultaneous requests from ONE document alone — a plausible cause of the
# observed finish_reason="error" responses (a backend/proxy-side failure
# consistent with hitting a concurrency ceiling).
#
# Now that Agents 3 and 5 are batched into one call each, and documents can
# run concurrently too (see main.py), a single BOTTLENECK here is the only
# thing that can enforce a real system-wide limit — no matter how many
# documents or agents try to call complete() at once, only this many actual
# HTTP requests are ever in flight. This is the one dial to turn if you still
# see finish_reason="error": lower it. If you have room (a higher published
# rate limit), you can raise it for more speed.
_GLOBAL_MAX_CONCURRENT = 4
_GLOBAL_SEM = asyncio.Semaphore(_GLOBAL_MAX_CONCURRENT)


class LLMClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self.total_tokens = 0

    def _call_sync(
        self, system_prompt: str, user_prompt: str, json_mode: bool,
        max_tokens: int = 8192,
    ) -> dict | str:
        """Synchronous LLM call. Runs in a thread to not block the event loop."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            # Was a flat 4096 for every call. Some calls (Agent 2 / Agent 4)
            # ask the model to return up to 12 fields, each with a full
            # verbatim quote, in ONE JSON response — that can genuinely
            # exceed 4096 tokens, causing finish_reason="length" (the model
            # was cut off mid-answer, not an error). Because temperature is 0,
            # a retry with the SAME limit fails the SAME way almost every
            # time — the fix is a bigger budget, not more retries.
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = httpx.post(
            OPENROUTER_URL,
            json=body,
            headers=headers,
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self.total_tokens += usage.get("total_tokens", 0)
        logger.info(f"LLM call: {usage.get('total_tokens', '?')} tokens (total: {self.total_tokens})")

        content = data["choices"][0]["message"]["content"]

        # The API can signal "no answer" two different ways: content=None, or
        # content="" (an empty string). Both mean the same thing to us, but
        # they are different Python values — checking only for None let an
        # empty string slip through and crash later inside json.loads("")
        # with the cryptic "Expecting value: line 1 column 1 (char 0)".
        # Catch both here, with one clear message.
        if content is None or not content.strip():
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            raise ValueError(
                f"LLM returned empty content (finish_reason={finish_reason})"
            )

        if json_mode:
            content = content.strip()
            if content.startswith("```"):
                # Strip a leading ```json / ``` fence. Guarded against a fence
                # with nothing after it on the same "line" (no newline to
                # split on), which would otherwise raise IndexError here.
                parts = content.split("\n", 1)
                content = parts[1] if len(parts) > 1 else ""
                content = content.rsplit("```", 1)[0]

            if not content.strip():
                # The whole response was just an empty ``` ``` fence with
                # nothing inside — same "no real answer" case as above, just
                # discovered after stripping markdown instead of before.
                raise ValueError("LLM response was an empty code fence with no JSON inside")

            return json.loads(content)
        return content

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        max_retries: int = 3,
        max_tokens: int = 8192,
        label: str | None = None,
    ) -> dict | str:
        """
        Async wrapper that runs the sync call in a thread.

        `label` is purely for logging — pass something like "a2_clause p.3-4"
        or "a3_retrieval:liability_cap" so a failure in the logs says WHICH
        call failed, not just "LLM attempt 1/3 failed". Optional; omit it and
        behaviour is unchanged.
        """
        tag = f" [{label}]" if label else ""
        for attempt in range(max_retries):
            try:
                # Acquire the GLOBAL slot before making the request, not just
                # a per-agent one. Whether this call is one of Agent 2's
                # chunks, Agent 3's batched call, or a call from a totally
                # different document running concurrently, it queues here
                # like everything else — this is what makes it safe to run
                # multiple documents at once (see main.py) without the whole
                # system's simultaneous request count spiralling.
                async with _GLOBAL_SEM:
                    result = await asyncio.to_thread(
                        self._call_sync, system_prompt, user_prompt, json_mode, max_tokens
                    )
                return result
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"LLM attempt {attempt+1}/{max_retries}{tag} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise


_client: LLMClient | None = None


def init_llm(api_key: str, model: str = DEFAULT_MODEL):
    global _client
    _client = LLMClient(api_key, model)


def get_llm() -> LLMClient:
    if _client is None:
        raise RuntimeError("Call init_llm(api_key) first")
    return _client
