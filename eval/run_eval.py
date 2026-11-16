"""Retrieval + leakage benchmark.   python -m eval.run_eval [cases.json] [--answers]

Metrics (cases with `expect_file`): recall@1, recall@k, MRR.
Leakage: every `forbid_file` case, plus an automatic check that each `expect_file` question, asked by every role
that must NOT see that file, never retrieves it. Any hit outside the asking role's tags also counts.
`--answers` also generates answers (needs GEMINI_API_KEY) and checks `keywords`.
"""
import json, sys
from pathlib import Path

from app import main as m


def run() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cases = json.loads(Path(args[0] if args else Path(__file__).parent / "cases.json").read_text())
    m.startup()
    file_tag = {f.name: t for t in m.TAGS for f in (m.DOCS / t).glob("*")}
    n = r1 = rk = checks = kw = kw_n = 0
    mrr, leaks = 0.0, []
    for c in cases:
        hits = m.retrieve(c["q"], c["role"])
        files = [h["file"] for h in hits]
        checks += 1
        if any(h["tag"] not in m.ROLE_ACCESS[c["role"]] for h in hits) or c.get("forbid_file") in files:
            leaks.append(c)
        if "expect_file" in c:
            n += 1
            ef = c["expect_file"]
            if ef in files:
                rk += 1
                r1 += files[0] == ef
                mrr += 1 / (files.index(ef) + 1)
            else:
                print(f"[MISS] {c['role']:8} {c['q']}")
            for role, tags in m.ROLE_ACCESS.items():
                if file_tag.get(ef) and file_tag[ef] not in tags:
                    checks += 1
                    if ef in [h["file"] for h in m.retrieve(c["q"], role)]:
                        leaks.append({**c, "role": role})
        if "--answers" in sys.argv and c.get("keywords"):
            kw_n += 1
            kw += all(k in "".join(m.generate(c["q"], hits, [], m.get_client())).lower() for k in c["keywords"])
    for c in leaks:
        print(f"[LEAK] {c['role']:8} {c['q']}")
    print(f"\nCases: {len(cases)}   recall@1: {r1}/{n}   recall@k: {rk}/{n}   MRR: {mrr / max(n, 1):.2f}")
    print(f"Leak checks run: {checks}   leaks: {len(leaks)} (must be 0)")
    if kw_n:
        print(f"Answer keyword checks: {kw}/{kw_n}")
    return 0 if not leaks and rk / max(n, 1) >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(run())
