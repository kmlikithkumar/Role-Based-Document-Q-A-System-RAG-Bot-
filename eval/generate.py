"""Build a larger benchmark from YOUR documents using Gemini (needs GEMINI_API_KEY).

    python -m eval.generate [chunks_per_file=6]      # writes eval/cases_generated.json
    python -m eval.run_eval eval/cases_generated.json

For each sampled passage Gemini writes one question it answers. The question is asked as the least-privileged
role that may read the file; run_eval then also checks that roles without access never retrieve it.
"""
import json, random, sys
from pathlib import Path

from app import main as m


def role_for(tag: str) -> str:
    return min((r for r in m.ROLE_ACCESS if r != "admin" and tag in m.ROLE_ACCESS[r]), key=lambda r: len(m.ROLE_ACCESS[r]))


def build(per_file: int = 6):
    client = m.get_client()
    assert client, "Set GEMINI_API_KEY first."
    m.startup()
    got = m.col.get(include=["documents", "metadatas"])
    items = list(zip(got["documents"], got["metadatas"]))
    random.seed(1)
    random.shuffle(items)
    cases, seen = [], {}
    for text, meta in items:
        if seen.get(meta["file"], 0) >= per_file:
            continue
        seen[meta["file"]] = seen.get(meta["file"], 0) + 1
        q = m.llm.complete(client, "Write ONE question an employee would ask that this passage alone answers. Use different words than the passage. Output only the question.",
                           [], text, max_tokens=512)
        cases.append({"role": role_for(meta["tag"]), "q": q, "expect_file": meta["file"]})
    out = Path(__file__).with_name("cases_generated.json")
    out.write_text(json.dumps(cases, indent=1))
    print(f"Wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    build(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
