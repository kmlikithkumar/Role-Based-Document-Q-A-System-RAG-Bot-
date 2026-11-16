"""The Gemini integration, run through the real google-genai SDK against a fake API that enforces the real rules."""
import json, sys, time

import httpx
import pytest

from tests.integration.helpers import HERE, Proc, free_port, login, start_app, wait


def boot(log, mode=""):
    port = free_port()
    llm = Proc([sys.executable, str(HERE / "fake_gemini.py"), str(port), str(log), mode])
    wait(f"http://127.0.0.1:{port}/docs")
    app, url = start_app(GEMINI_API_KEY="test-key", GEMINI_BASE_URL=f"http://127.0.0.1:{port}")
    return app, llm, url


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    log = tmp_path_factory.mktemp("llm") / "calls.jsonl"
    log.write_text("")
    app, llm, url = boot(log)
    yield url, str(log)
    app.stop(); llm.stop()


def calls(log):
    return [json.loads(x) for x in open(log) if x.strip()]


def ask(url, h, q, chat_id=None):
    t0, events = time.time(), []
    with httpx.stream("POST", url + "/api/ask", json={"question": q, "chat_id": chat_id}, headers=h, timeout=30) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line:
                events.append((json.loads(line), time.time() - t0))
    return events


def test_restricted_text_never_reaches_the_llm(stack):
    url, log = stack
    q = "How many days of annual leave do I get?"
    assert ask(url, login(url, "carol", "carol123"), q)[-1][0]["type"] == "done"
    assert "paid annual leave" not in json.dumps(calls(log)[-1]["contents"])      # HR policy text stays out of the prompt
    ask(url, login(url, "alice", "alice123"), q)
    assert "paid annual leave" in json.dumps(calls(log)[-1]["contents"])


def test_key_model_and_parameters_follow_the_current_rules(stack):
    url, log = stack
    ask(url, login(url, "bob", "bob123"), "When can we deploy to production?")
    last = calls(log)[-1]
    assert last["key"] == "test-key" and last["model"] == "gemini-3.5-flash-lite" and last["stream"] is True
    assert not {"temperature", "topP", "topK"} & set(last.get("generationConfig", {}))   # deprecated for current models
    assert "ONLY the numbered context" in json.dumps(last["systemInstruction"])


def test_answer_streams_incrementally(stack):
    url, _ = stack
    ev = ask(url, login(url, "bob", "bob123"), "When can we deploy to production?")
    tokens = [(e["text"], t) for e, t in ev if e["type"] == "token"]
    assert "".join(x for x, _ in tokens) == "Answer from context [1]."
    assert ev[-1][1] - tokens[0][1] > 0.5          # first token arrives well before the answer is complete


def test_followup_is_rewritten_and_history_is_valid(stack):
    url, log = stack
    h = login(url, "alice", "alice123")
    cid = ask(url, h, "How many days of annual leave do I get?")[0][0]["id"]
    before = len(calls(log))
    assert ask(url, h, "What about sick leave?", cid)[-1][0]["type"] == "done"
    new = calls(log)[before:]
    assert any(not c["stream"] for c in new)                                       # standalone-query rewrite
    streamed = [c for c in new if c["stream"]][-1]
    assert [m["role"] for m in streamed["contents"]] == ["user", "model", "user"]  # Gemini names the assistant "model"


@pytest.mark.parametrize("mode,needle", [("quota", "quota or rate limit"), ("badkey", "rejected the API key"), ("nomodel", "LLM_MODEL")])
def test_api_errors_are_explained_not_dumped(tmp_path, mode, needle):
    app, llm, url = boot(tmp_path / "c.jsonl", mode)
    try:
        ev = [e for e, _ in ask(url, login(url, "alice", "alice123"), "How many days of annual leave do I get?")]
        kinds = [e["type"] for e in ev]
        assert "sources" in kinds and kinds[-1] == "error"                          # passages are still shown
        assert needle in ev[-1]["message"]
        assert "RESOURCE_EXHAUSTED" not in ev[-1]["message"] and "INVALID_ARGUMENT" not in ev[-1]["message"]   # no raw API text
    finally:
        app.stop(); llm.stop()
