"""Standard gates G2-G5 (docs/MILESTONES.md).

    python scripts/check_scope.py M2.1 [--base main]  # G2 scope, G3 expected files, G4 CLAUDE.md
    python scripts/check_scope.py --web-guard         # G5: no web/ before tag m3-done

Changed files = commits since the merge-base with --base, plus uncommitted and untracked files.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCOPE_FILE = ROOT / "scripts" / "scope.yaml"
PROTECTED = {
    "G3": ("fixtures/expected/**", "Claude Code never edits expected files"),
    "G4": ("CLAUDE.md", "only the tech lead edits CLAUDE.md"),
}


@cache
def glob_regex(glob: str) -> re.Pattern[str]:
    """Translate a path glob (`*` within a segment, `**` across segments) to a regex."""
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, globs: list[str]) -> bool:
    return any(glob_regex(glob).match(path) for glob in globs)


def load_scope() -> tuple[list[str], dict[str, list[str]]]:
    data = yaml.safe_load(SCOPE_FILE.read_text(encoding="utf-8"))
    return list(data["global"]), {str(k): list(v) for k, v in data["sessions"].items()}


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def changed_files(base: str) -> set[str]:
    merge_base = git("merge-base", "HEAD", base)[0]
    files = set(git("diff", "--name-only", "--no-renames", merge_base, "HEAD"))
    files |= set(git("diff", "--name-only", "--no-renames", "HEAD"))
    files |= set(git("ls-files", "--others", "--exclude-standard"))
    return files


def violations(changed: set[str], session: str) -> list[str]:
    global_allowed, sessions = load_scope()
    if session not in sessions:
        return [f"unknown session {session!r}; known: {', '.join(sessions)}"]
    allowed = sessions[session] + global_allowed
    problems = [
        f"G2 out of scope for {session}: {p}" for p in sorted(changed) if not matches(p, allowed)
    ]
    for gate, (glob, why) in PROTECTED.items():
        problems += [f"{gate} {why}: {p}" for p in sorted(changed) if matches(p, [glob])]
    return problems


def web_guard() -> list[str]:
    if (ROOT / "web").exists() and not git("tag", "--list", "m3-done"):
        return ["G5 web/ exists but tag m3-done does not (no UI before M3 is green)"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standard gates G2-G5")
    parser.add_argument("session", nargs="?", help="session id, e.g. M0 or M2.1")
    parser.add_argument("--base", default="main", help="branch the session started from")
    parser.add_argument("--web-guard", action="store_true", help="run G5 only")
    args = parser.parse_args(argv)
    problems = web_guard() if args.web_guard else []
    if args.session:
        problems += violations(changed_files(args.base), args.session.upper())
    elif not args.web_guard:
        parser.error("give a session id and/or --web-guard")
    for problem in problems:
        print(problem)
    if not problems:
        print("scope checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
