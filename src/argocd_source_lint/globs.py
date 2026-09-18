from __future__ import annotations

import re


def match_glob(pattern: str, candidate: str) -> bool:
    """ArgoCD's glob semantics, shared by the `git` ApplicationSet
    generator (`directories`/`files`) and `project-scope-violation`
    (`sourceRepos`/`destinations`): `*` matches within one `/`-separated
    segment, `**` crosses `/` — unlike `fnmatch`, where a lone `*`
    already crosses `/`. `namespace`/`server`/`name` patterns never
    contain `/` in practice, so this is equally correct there."""
    parts = pattern.split("**")
    escaped = [re.escape(part).replace(r"\*", "[^/]*").replace(r"\?", ".") for part in parts]
    return re.match("^" + ".*".join(escaped) + "$", candidate) is not None
