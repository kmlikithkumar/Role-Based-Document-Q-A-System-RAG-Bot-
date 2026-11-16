"""Google Gemini (Gemini Developer API, `google-genai` SDK). Every model call in the app goes through this file.

Notes from Google's docs for current models (3.5 Flash-Lite, 3.6/3.8 Flash): do not send temperature, top_p or top_k
(deprecated), never end a request with a "model" turn, and remember that thinking tokens count toward max_output_tokens.
"""
import os

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # cheap and stable; for the strongest answers set LLM_MODEL=gemini-3.8-flash


def model_name() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


def get_client():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    from google import genai
    from google.genai import types
    base = os.getenv("GEMINI_BASE_URL")  # only for tests with a fake server
    return genai.Client(api_key=key, http_options=types.HttpOptions(base_url=base) if base else None)


def _contents(history: list[dict], user_text: str) -> list[dict]:
    role = {"assistant": "model"}  # Gemini calls the assistant "model"
    turns = [{"role": role.get(m["role"], m["role"]), "parts": [{"text": m["content"]}]} for m in history]
    return turns + [{"role": "user", "parts": [{"text": user_text}]}]


def _config(system: str, max_tokens: int):
    from google.genai import types
    kw = {"system_instruction": system, "max_output_tokens": max_tokens}
    level = os.getenv("GEMINI_THINKING")  # optional: minimal | low | medium | high. Unset = the model's default
    if level:
        kw["thinking_config"] = types.ThinkingConfig(thinking_level=level)
    return types.GenerateContentConfig(**kw)


def complete(client, system: str, history: list[dict], user_text: str, max_tokens: int = 512) -> str:
    r = client.models.generate_content(model=model_name(), contents=_contents(history, user_text), config=_config(system, max_tokens))
    return (r.text or "").strip()


def stream(client, system: str, history: list[dict], user_text: str, max_tokens: int = 2048):
    got = False
    for chunk in client.models.generate_content_stream(model=model_name(), contents=_contents(history, user_text), config=_config(system, max_tokens)):
        if chunk.text:
            got = True
            yield chunk.text
    if not got:
        yield "(The AI service returned no answer. It may have been stopped by a safety filter. The matching passages are listed below.)"


def friendly_error(e: Exception) -> str:
    """Plain-language message for the user; the real error goes to the server log only."""
    code, text = getattr(e, "code", None) or getattr(e, "status_code", None), str(e).lower()
    print("LLM error:", e)
    if code == 401 or "api key not valid" in text or "api_key_invalid" in text:
        return "The Gemini API rejected the API key. An administrator should check GEMINI_API_KEY (create one at aistudio.google.com/apikey)."
    if code == 403:
        return "The Gemini API denied access for this key. An administrator should check that the key's project may use the Gemini API."
    if code == 404:
        return f"The model '{model_name()}' is not available for this key. An administrator should set LLM_MODEL to a current model such as gemini-3.5-flash-lite or gemini-3.8-flash."
    if code == 429:
        return "The Gemini API quota or rate limit was reached (free-tier limits are low). Wait a minute and try again, or enable billing for the key's project."
    if "failed_precondition" in text or "location is not supported" in text:
        return "The Gemini API is not available for this key's region or plan. An administrator may need to enable billing or use a supported region."
    if isinstance(code, int) and code >= 500:
        return "The Gemini API is temporarily unavailable. Please try again shortly."
    return "Could not generate an answer. The matching passages are listed below."
