"""Write docs/ratings_draft.md from the latest commentary artefact (never ratings.json).

    python scripts/make_ratings_draft.py [artifacts/commentary/company_a.json]

Lays out each displayed paragraph for the tech lead to rate (faithful, cited). It scores nothing.
The header carries `claims_sha256`: put it in `ratings.json`, which then counts only for this run.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from finintel.commentary.ratings import claims_sha256

ROOT = Path(__file__).resolve().parent.parent


def one_line(text: str) -> str:
    t = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"])", t)
    line, i = parts[0], 1
    while (line.count('"') % 2 == 1 or (len(line) < 60 and i == 1)) and i < len(parts) and i < 4:
        line, i = f"{line} {parts[i]}", i + 1
    line = line.strip()
    return line if len(line) <= 220 else line[:217].rstrip() + "..."


def pages(cites: list[dict[str, int]]) -> str:
    seen = sorted({p for c in cites for p in range(c["page"], c["page_end"] + 1)})
    return ", ".join(str(p) for p in seen) or "none"


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else ROOT / "artifacts" / "commentary" / "company_a.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out = data["output"]
    rows = [
        (f"{t['topic']}:{n}", t["topic"], p)
        for t in out["topics"]
        for n, p in enumerate(t["paragraphs"])
    ]
    rows += [
        (f"executive_summary:{n}", "executive_summary", p)
        for n, p in enumerate(out["executive_summary"]["bullets"])
    ]
    assert {r[0] for r in rows} == set(data["claims"]), "ids differ from the artefact claims"
    lines = [
        "# Ratings draft (company_a, M5.2 commentary)",
        "",
        "Unrated. Nothing here is a score. Rate each paragraph (faithful, cited) and save",
        "`fixtures/expected/ratings.json` yourself, including the `claims_sha256` below: ratings count only for this run.",
        "",
        f"- claims_sha256: `{claims_sha256(data['claims'])}`",
        f"- Source: `{path.relative_to(ROOT) if path.is_absolute() and ROOT in path.parents else path}`, mode `{out['mode']}`, "
        f"model `{(out['model'] or {}).get('model_id')}`, prompt `{out['prompt_version']}`, schema `{out['schema_version']}`.",
        f"- Paragraphs: {len(rows)} (topics, then the executive summary). `paragraph_id` is the id the scorer expects.",
        "- `quoted from pages`: computed by code from each verified quote. `figures from pages`: computed by code from the",
        "  packs, one entry per placeholder, with the page(s) that print the figure (or its inputs).",
        "- `claim` is mechanical: the first sentence (closed over an open quotation; two sentences if the first is a short label).",
        "",
    ]
    for pid, section, p in rows:
        figs = (
            "; ".join(
                f"{f['rendered'] or 'n/a'} <- p. {', '.join(map(str, f['pages'])) or 'none'}"
                for f in p["figures"]
            )
            or "none"
        )
        lines += [
            f"## {pid}",
            "",
            f"- **paragraph_id:** `{pid}`",
            f"- **section:** {section}",
            f"- **quoted from pages:** {pages(p['citations'])}",
            f"- **figures from pages:** {figs}",
            f"- **claim:** {one_line(p['rendered'])}",
            "",
            "> " + " ".join(p["rendered"].split()),
            "",
        ]
    target = ROOT / "docs" / "ratings_draft.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)} ({len(rows)} paragraphs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
