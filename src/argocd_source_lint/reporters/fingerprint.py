from __future__ import annotations

import hashlib

from argocd_source_lint.models import Finding


def stable_fingerprint(finding: Finding) -> str:
    """A hash stable across runs for the same underlying issue --
    content-based (rule + file + application + message), not the
    finding's position in a list, so a re-run with an unrelated change
    elsewhere doesn't shuffle it. Shared by the GitLab Code Quality
    `fingerprint` field and the SARIF `partialFingerprints`, both of
    which exist specifically so a consumer can recognize "the same"
    finding across runs instead of treating every run's findings as new."""
    identity = (
        f"{finding.rule_id}|{finding.file.as_posix()}|{finding.application}|{finding.message}"
    )
    return hashlib.md5(identity.encode("utf-8")).hexdigest()
