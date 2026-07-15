"""
Report Generator for Audit and Construction Framework.

Generates structured markdown reports with summaries and detailed corrections.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from corrections_templates import get_audit_pass_corrections, get_construction_phase_corrections



class ReportGenerator:
    """Generate markdown reports for audit and construction reviews."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path.cwd()
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_audit_report(
        self,
        notebook_name: str,
        pass_num: int,
        issues: List[Dict[str, Any]],
        risk_score: str = "Moderate",
        gate_decision: str = "PROCEED",
        additional_context: Optional[Dict] = None
    ) -> Path:
        """
        Generate a markdown report for an audit pass.
        
        Args:
            notebook_name: Name of the notebook being audited
            pass_num: Audit pass number (1-6)
            issues: List of issues found, each with 'type', 'severity', 'description'
            risk_score: Overall risk assessment (Low/Moderate/High)
            gate_decision: Gate decision (PROCEED/PROCEED_WITH_WARNINGS/BLOCK)
            additional_context: Extra metadata to include
            
        Returns:
            Path to the generated report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"audit_report_{Path(notebook_name).stem}_pass{pass_num}_{timestamp}.md"
        report_path = self.output_dir / report_filename
        
        corrections = get_audit_pass_corrections(pass_num)
        pass_name = corrections.get("name", f"Pass {pass_num}")
        pass_desc = corrections.get("description", "")
        
        # Build report content
        lines = []
        lines.append(f"# Audit Report: {notebook_name}")
        lines.append(f"## Pass {pass_num}: {pass_name}")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().isoformat()}")
        lines.append(f"**Risk Level**: {risk_score}")
        lines.append(f"**Gate Decision**: `{gate_decision}`")
        lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # Overview
        lines.append("## Overview")
        lines.append(f"{pass_desc}")
        lines.append("")
        
        # Issues Summary
        lines.append("## Issues Summary")
        if not issues:
            lines.append("[+] No issues detected.")
        else:
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            sorted_issues = sorted(issues, key=lambda x: severity_order.get(x.get("severity", "MEDIUM"), 99))
            
            lines.append(f"Found **{len(issues)}** issue(s):\n")
            for i, issue in enumerate(sorted_issues, 1):
                severity = issue.get("severity", "MEDIUM")
                severity_emoji = {"CRITICAL": "[C]", "HIGH": "[H]", "MEDIUM": "[M]", "LOW": "[L]"}
                emoji = severity_emoji.get(severity, "[*]")
                issue_type = issue.get("type", "Unknown")
                lines.append(f"{i}. {emoji} **{issue_type}** ({severity})")
                lines.append(f"   - {issue.get('description', 'No description')}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Detailed Corrections
        lines.append("## Detailed Corrections")
        lines.append("")
        
        if corrections and "corrections" in corrections:
            for idx, correction in enumerate(corrections["corrections"], 1):
                lines.append(f"### Correction {idx}: {correction.get('issue', 'Unknown')}")
                lines.append(f"**Severity**: {correction.get('severity', 'MEDIUM')}")
                lines.append("")
                
                lines.append("#### Problem")
                lines.append(f"{correction.get('problem', 'N/A')}")
                lines.append("")
                
                lines.append("#### Example (What NOT to do)")
                lines.append("```python")
                lines.append(correction.get('bad_example', 'No example available'))
                lines.append("```")
                lines.append("")
                
                lines.append("#### Solution (What to do instead)")
                lines.append("```python")
                lines.append(correction.get('good_example', 'No example available'))
                lines.append("```")
                lines.append("")
                
                lines.append("#### Why It Matters")
                lines.append(f"{correction.get('why_it_matters', 'N/A')}")
                lines.append("")
        
        # Gate Decision Details
        lines.append("---")
        lines.append("")
        lines.append("## Gate Decision")
        lines.append("")
        if gate_decision == "PROCEED":
            lines.append("[+] **PROCEED** to next pass. No blocking issues detected.")
        elif gate_decision == "PROCEED_WITH_WARNINGS":
            lines.append("[!] **PROCEED WITH WARNINGS** to next pass. Address flagged issues before deployment.")
        else:
            lines.append("[X] **BLOCK** — Critical issues must be resolved before proceeding.")
        
        # Additional context
        if additional_context:
            lines.append("")
            lines.append("---")
            lines.append("## Additional Context")
            for key, value in additional_context.items():
                lines.append(f"- **{key}**: {value}")
        
        # Write report
        content = "\n".join(lines)
        report_path.write_text(content, encoding="utf-8")
        
        return report_path
    
    def generate_construction_report(
        self,
        notebook_name: str,
        phase_num: int,
        findings: List[Dict[str, Any]],
        status: str = "In Progress",
        gate_decision: str = "PROCEED",
        additional_context: Optional[Dict] = None
    ) -> Path:
        """
        Generate a markdown report for a construction phase.
        
        Args:
            notebook_name: Name of the notebook being built
            phase_num: Construction phase number (1-3)
            findings: List of findings/recommendations
            status: Current phase status
            gate_decision: Gate decision (PROCEED/PROCEED_WITH_WARNINGS/BLOCK)
            additional_context: Extra metadata
            
        Returns:
            Path to the generated report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"construction_report_{Path(notebook_name).stem}_phase{phase_num}_{timestamp}.md"
        report_path = self.output_dir / report_filename
        
        corrections = get_construction_phase_corrections(phase_num)
        phase_name = corrections.get("name", f"Phase {phase_num}")
        phase_desc = corrections.get("description", "")
        
        lines = []
        lines.append(f"# Construction Report: {notebook_name}")
        lines.append(f"## Phase {phase_num}: {phase_name}")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().isoformat()}")
        lines.append(f"**Status**: {status}")
        lines.append(f"**Gate Decision**: `{gate_decision}`")
        lines.append("")
        
        lines.append("---")
        lines.append("")
        
        # Overview
        lines.append("## Overview")
        lines.append(f"{phase_desc}")
        lines.append("")
        
        # Findings Summary
        lines.append("## Findings & Recommendations")
        if not findings:
            lines.append("[+] All best practices followed.")
        else:
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            sorted_findings = sorted(findings, key=lambda x: severity_order.get(x.get("severity", "MEDIUM"), 99))
            
            lines.append(f"Found **{len(findings)}** finding(s):\n")
            for i, finding in enumerate(sorted_findings, 1):
                severity = finding.get("severity", "MEDIUM")
                severity_emoji = {"CRITICAL": "[C]", "HIGH": "[H]", "MEDIUM": "[M]", "LOW": "[L]"}
                emoji = severity_emoji.get(severity, "[*]")
                finding_type = finding.get("type", "Unknown")
                lines.append(f"{i}. {emoji} **{finding_type}** ({severity})")
                lines.append(f"   - {finding.get('description', 'No description')}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Detailed Recommendations
        lines.append("## Detailed Recommendations")
        lines.append("")
        
        if corrections and "corrections" in corrections:
            for idx, correction in enumerate(corrections["corrections"], 1):
                lines.append(f"### Recommendation {idx}: {correction.get('issue', 'Unknown')}")
                lines.append(f"**Severity**: {correction.get('severity', 'MEDIUM')}")
                lines.append("")
                
                lines.append("#### Current Issue")
                lines.append(f"{correction.get('problem', 'N/A')}")
                lines.append("")
                
                lines.append("#### Current Practice (to improve)")
                lines.append("```python")
                lines.append(correction.get('bad_example', 'No example available'))
                lines.append("```")
                lines.append("")
                
                lines.append("#### Recommended Approach")
                lines.append("```python")
                lines.append(correction.get('good_example', 'No example available'))
                lines.append("```")
                lines.append("")
                
                lines.append("#### Benefits")
                lines.append(f"{correction.get('why_it_matters', 'N/A')}")
                lines.append("")
        
        # Gate Decision
        lines.append("---")
        lines.append("")
        lines.append("## Gate Decision")
        lines.append("")
        if gate_decision == "PROCEED":
            lines.append("[+] **PROCEED** to next phase. Phase is ready to complete.")
        elif gate_decision == "PROCEED_WITH_WARNINGS":
            lines.append("[!] **PROCEED WITH WARNINGS** — address recommendations before moving forward.")
        else:
            lines.append("[X] **BLOCK** — critical issues must be resolved before continuing.")
        
        # Additional context
        if additional_context:
            lines.append("")
            lines.append("---")
            lines.append("## Checklist")
            for key, value in additional_context.items():
                checkbox = "[+]" if value else "[ ]"
                lines.append(f"- [{checkbox}] {key}")
        
        # Write report
        content = "\n".join(lines)
        report_path.write_text(content, encoding="utf-8")
        
        return report_path
    
    def create_summary_index(self, reports: List[Path]) -> Path:
        """
        Create an index markdown file linking all generated reports.
        
        Args:
            reports: List of report file paths
            
        Returns:
            Path to the index file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        index_path = self.output_dir / f"report_index_{timestamp}.md"
        
        lines = []
        lines.append("# Report Index")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("")
        
        if not reports:
            lines.append("No reports generated yet.")
        else:
            lines.append("## Generated Reports")
            lines.append("")
            for report_path in reports:
                rel_path = report_path.relative_to(self.output_dir)
                lines.append(f"- [{report_path.name}]({rel_path})")
        
        content = "\n".join(lines)
        index_path.write_text(content, encoding="utf-8")
        
        return index_path
