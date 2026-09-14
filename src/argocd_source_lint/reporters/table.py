from __future__ import annotations

from rich.console import Console
from rich.table import Table

from argocd_source_lint.models import Finding, Severity

_SEVERITY_STYLE = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "yellow",
    Severity.INFO: "cyan",
    Severity.UNVERIFIABLE: "bold magenta",
}


def render_findings(console: Console, findings: list[Finding]) -> None:
    if not findings:
        console.print("[green]No issues detected.[/green]")
        return

    table = Table(show_lines=False)
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("Application")
    table.add_column("File")
    table.add_column("Message")

    for finding in findings:
        style = _SEVERITY_STYLE.get(finding.severity, "")
        location = finding.file.as_posix()
        if finding.line is not None:
            location += f":{finding.line}"
        table.add_row(
            f"[{style}]{finding.severity.value}[/{style}]",
            finding.rule_id,
            finding.application,
            location,
            finding.message,
        )
    console.print(table)
