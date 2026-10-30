#!/usr/bin/env python3
"""Complexity score for a task, from the files it is expected to touch.

Used by the generated preflight skill to route a task: trivial tasks go
straight to coding, medium tasks enter plan mode first, high tasks are also
decomposed into sub-tasks. The score is a linear sum so it can be tuned from
report data; weights and thresholds live in manifest task_docs.complexity.

Usage:
  python complexity.py --project DIR --files a.ts b.ts ... [--new-archetype] [--json]

Factors:
  files             number of files listed, times weights.files
  cross_module      the files span more than one module (architecture.modules[].path)
  security_surface  any file matches a security.checks[].paths glob
  new_archetype     passed by preflight when the task creates a file type with no sibling

Stdlib only. Exit 0 with JSON on stdout; exit 1 with a JSON error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_doc import find_claude_dir, load_manifest, normalize_path, path_matches  # noqa: E402

DEFAULT_WEIGHTS = {"files": 1.0, "cross_module": 3.0, "security_surface": 3.0, "new_archetype": 2.0}
DEFAULT_THRESHOLDS = {"medium": 4.0, "high": 8.0}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=None, help="Project directory (default: $CLAUDE_PROJECT_DIR, else cwd)")
    p.add_argument("--files", nargs="*", default=[], help="Project-relative paths the task will touch")
    p.add_argument("--new-archetype", action="store_true", help="The task creates a file type with no sibling")
    p.add_argument("--json", action="store_true", help="(default) JSON output")
    return p.parse_args()


def numbers(block, defaults):
    out = dict(defaults)
    for k, v in (block or {}).items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def module_of(rel, modules):
    """Name of the module whose path prefixes rel, longest prefix wins."""
    best = None
    for m in modules:
        path = normalize_path(str(m.get("path") or "")).strip("/")
        if not path:
            continue
        if rel == path or rel.startswith(path + "/"):
            if best is None or len(path) > len(best[1]):
                best = (m.get("name") or path, path)
    return best[0] if best else None


def main():
    args = parse_args()
    start = args.project or os.environ.get("CLAUDE_PROJECT_DIR") or None
    claude_dir = find_claude_dir(start)
    manifest = load_manifest(claude_dir)
    cfg = (manifest.get("task_docs") or {}).get("complexity") or {}
    weights = numbers(cfg.get("weights"), DEFAULT_WEIGHTS)
    thresholds = numbers(cfg.get("thresholds"), DEFAULT_THRESHOLDS)

    files = [normalize_path(f).lstrip("./") for f in args.files if f]
    modules = [m for m in (manifest.get("architecture") or {}).get("modules") or [] if isinstance(m, dict)]
    checks = [c for c in (manifest.get("security") or {}).get("checks") or [] if isinstance(c, dict)]
    security_globs = [g for c in checks for g in (c.get("paths") or []) if isinstance(g, str)]

    touched_modules = sorted({m for m in (module_of(f, modules) for f in files) if m})
    security_files = [f for f in files if security_globs and path_matches(f, security_globs)]

    factors = {
        "files": len(files),
        "cross_module": 1 if len(touched_modules) > 1 else 0,
        "security_surface": 1 if security_files else 0,
        "new_archetype": 1 if args.new_archetype else 0,
    }
    score = sum(factors[k] * weights.get(k, 0.0) for k in factors)
    if score >= thresholds["high"]:
        tier = "high"
    elif score >= thresholds["medium"]:
        tier = "medium"
    else:
        tier = "trivial"

    routing = {
        "trivial": "Proceed to coding with the brief.",
        "medium": "Enter plan mode before editing. The plan names target files and order, the pattern each file follows, security and tenancy implications, and the rollback story.",
        "high": "Enter plan mode and decompose into sub-tasks, each with its own task doc and scope, before editing.",
    }[tier]

    print(json.dumps({
        "score": round(score, 2),
        "tier": tier,
        "routing": routing,
        "factors": factors,
        "weights": weights,
        "thresholds": thresholds,
        "modules_touched": touched_modules,
        "security_files": security_files,
        "claude_dir": claude_dir,
    }, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        sys.exit(1)
