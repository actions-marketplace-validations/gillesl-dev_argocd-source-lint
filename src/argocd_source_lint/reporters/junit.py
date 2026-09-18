from __future__ import annotations

from xml.etree import ElementTree as ET

from argocd_source_lint.models import Finding, Severity

# JUnit has no native "warning"/"info" level, only pass/failure/error/
# skipped. error and unverifiable are the two severities that actually
# block CI by default (see cli._exit_code) -- mapped to <failure>.
# warning/info become <skipped> rather than a plain, silent pass: they
# ARE something to look at, just not blocking, and a skipped testcase
# renders visually distinct (grey, not green) in every consumer that
# matters here (Jenkins, GitLab, Azure DevOps).
_FAILING = {Severity.ERROR, Severity.UNVERIFIABLE}


def render_findings(findings: list[Finding]) -> str:
    failures = sum(1 for finding in findings if finding.severity in _FAILING)
    skipped = len(findings) - failures

    attrs = {
        "name": "argocd-source-lint",
        "tests": str(len(findings)),
        "failures": str(failures),
        "errors": "0",
        "skipped": str(skipped),
        "time": "0",
    }
    testsuite = ET.Element("testsuite", attrs)
    for finding in findings:
        testsuite.append(_testcase(finding))

    testsuites = ET.Element("testsuites", attrs)
    testsuites.append(testsuite)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(testsuites, encoding="unicode")


def _testcase(finding: Finding) -> ET.Element:
    attrs = {
        "classname": finding.rule_id,
        "name": finding.message,
        "file": finding.file.as_posix(),
        "time": "0",
    }
    if finding.line is not None:
        attrs["line"] = str(finding.line)

    testcase = ET.Element("testcase", attrs)
    if finding.severity in _FAILING:
        ET.SubElement(
            testcase, "failure", {"message": finding.message, "type": finding.severity.value}
        )
    else:
        ET.SubElement(testcase, "skipped", {"message": f"{finding.severity.value}: not blocking"})
    return testcase
