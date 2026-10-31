#!/usr/bin/env python3
"""Complexity score for a task, from the files it is expected to touch.

Used by the generated preflight skill to route a task: trivial tasks go
straight to coding, medium tasks enter plan mode first, high tasks are also
decomposed into sub-tasks. The score is a linear sum so it can be tuned from
report data; weights and thresholds live in manifest task_docs.complexity.

Usage:
  python complexity.py --project DIR --files a.ts b.ts ... [--new-archetype]

Files may be project-relative or absolute (absolute paths are made relative
to the project); duplicates are dropped; matching is case-insensitive.

Factors:
  files             number of distinct files, times weights.files
  cross_module      the files span more than one module (architecture.modules[].path, a directory)
  security_surface  any file matches a security.checks[].paths glob (a check without paths does not count)
  new_archetype     passed by preflight when the task creates a file type with no sibling

Stdlib only. Exit 0 with JSON on stdout; exit 1 with a JSON error for a
manifest whose weights are not finite numbers or whose thresholds are inverted.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_doc import (  # noqa: E402
    find_claude_dir, load_manifest, normalize_path, path_matches, project_root, rel_project_path, strip_dot_slash,
)

DEFAULT_WEIGHTS = {"files": 1.0, "cross_module": 3.0, "security_surface": 3.0, "new_archetype": 2.0}
DEFAULT_THRESHOLDS = {"medium": 4.0, "high": 8.0}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=None, help="Project directory (default: $CLAUDE_PROJECT_DIR, else cwd)")
    p.add_argument("--files", nargs="*", default=[], help="Paths the task will touch")
    p.add_argument("--new-archetype", action="store_true", help="The task creates a file type with no sibling")
    return p.parse_args()


def numbers(block, defaults, what):
    out = dict(defaults)
    if block is None:
        return out
    if not isinstance(block, dict):
        raise ValueError(f"task_docs.complexity.{what} must be an object")
    for k, v in block.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"task_docs.complexity.{what}.{k} is not a number: {v!r}")
        if not math.isfinite(f) or f < 0:
            raise ValueError(f"task_docs.complexity.{what}.{k} must be a finite non-negative number")
        out[k] = f
    return out


def module_dir(m):
    path = strip_dot_slash(normalize_path(str(m.get("path") or ""))).strip("/")
    for suffix in ("/**", "/*"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return path.lower()


def module_of(rel, modules):
    """Name of the module whose directory prefixes rel; longest prefix wins."""
    best = None
    low = rel.lower()
    for m in modules:
        d = module_dir(m)
        if d and (low == d or low.startswith(d + "/")):
            if best is None or len(d) > len(best[1]):
                best = (m.get("name") or d, d)
    return best[0] if best else None


def main():
    args = parse_args()
    start = args.project or os.environ.get("CLAUDE_PROJECT_DIR") or None
    claude_dir = find_claude_dir(start)
    root = project_root(claude_dir) if claude_dir else os.path.abspath(start or os.getcwd())
    manifest = load_manifest(claude_dir)
    cfg = (manifest.get("task_docs") or {}).get("complexity") or {}
    weights = numbers(cfg.get("weights"), DEFAULT_WEIGHTS, "weights")
    thresholds = numbers(cfg.get("thresholds"), DEFAULT_THRESHOLDS, "thresholds")
    if thresholds["medium"] >= thresholds["high"]:
        raise ValueError("task_docs.complexity.thresholds.medium must be below thresholds.high")

    files = []
    for f in args.files:
        if not f:
            continue
        rel = rel_project_path(f, root, base=root) if os.path.isabs(normalize_path(f)) or ":" in f[:2] else None
        rel = rel if rel is not None else strip_dot_slash(normalize_path(f))
        rel = rel.strip("/")
        if rel and rel.lower() not in {x.lower() for x in files}:
            files.append(rel)

    modules = [m for m in (manifest.get("architecture") or {}).get("modules") or [] if isinstance(m, dict)]
    security_globs = []
    for c in (manifest.get("security") or {}).get("checks") or []:
        if not isinstance(c, dict):
            continue
        paths = c.get("paths")
        if isinstance(paths, str):
            paths = [paths]
        security_globs.extend(g for g in (paths or []) if isinstance(g, str) and g.strip())

    touched_modules = sorted({m for m in (module_of(f, modules) for f in files) if m})
    security_files = [f for f in files if security_globs and path_matches(f, security_globs)]

    factors = {
        "files": len(files),
        "cross_module": 1 if len(touched_modules) > 1 else 0,
        "security_surface": 1 if security_files else 0,
        "new_archetype": 1 if args.new_archetype else 0,
    }
    score = sum(factors[k] * weights.get(k, 0.0) for k in factors)
    tier = "high" if score >= thresholds["high"] else "medium" if score >= thresholds["medium"] else "trivial"
    routing = {
        "trivial": "Proceed to coding with the brief.",
        "medium": "Enter plan mode before editing. The plan names target files and order, the pattern each "
                  "file follows, security and tenancy implications, and the rollback story.",
        "high": "Enter plan mode and decompose into sub-tasks, each with its own task doc and scope, before editing.",
    }[tier]
    print(json.dumps({
        "score": round(score, 2),
        "tier": tier,
        "routing": routing,
        "factors": factors,
        "weights": weights,
        "thresholds": thresholds,
        "files": files,
        "modules_touched": touched_modules,
        "security_files": security_files,
        "claude_dir": claude_dir,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        sys.exit(1)
