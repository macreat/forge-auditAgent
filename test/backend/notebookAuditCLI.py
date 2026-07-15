#!/usr/bin/env python3
"""
Notebook Audit & Construction Framework CLI

Interactive tool for auditing and constructing Jupyter notebooks following
the 6-pass audit framework or 3-phase construction framework.

Usage:
    python notebookAuditCLI.py                        # Interactive mode
    python notebookAuditCLI.py --notebook path/to/notebook.ipynb
    python notebookAuditCLI.py --mode audit --pass 2
    python notebookAuditCLI.py --mode audit --all     # All 6 passes
    python notebookAuditCLI.py --mode construction --phase 1
    python notebookAuditCLI.py --mode construction --all  # All 3 phases
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple, List
import json

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from corrections_templates import (
    get_all_audit_passes,
    get_all_construction_phases,
    get_audit_pass_corrections,
    get_construction_phase_corrections
)
from report_generator import ReportGenerator
from AuditFramework.audit_engine import run_all_mechanical_passes
from ConstructionFramework.construction_engine import run_all_construction_phases


_OUTPUT_DIR: Path | None = None


def _get_output_dir() -> Path:
    global _OUTPUT_DIR
    if _OUTPUT_DIR is None:
        _OUTPUT_DIR = Path(__file__).parent / "outDir"
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return _OUTPUT_DIR


def find_notebooks(directory: Optional[Path] = None) -> List[Path]:
    """
    Find all Jupyter notebooks in directory and subdirectories.
    
    Args:
        directory: Directory to search (default: ../nbs relative to scripts, or current dir)
        
    Returns:
        List of notebook paths
    """
    if directory is None:
        # Default to '../nbs' (reference/nbs from scripts/), fallback to current directory
        script_dir = Path(__file__).parent
        nbs_dir = script_dir / "nbs"
        if nbs_dir.exists():
            directory = nbs_dir
        else:
            directory = Path.cwd()
    
    directory = Path(directory)
    notebooks = list(directory.glob("**/*.ipynb"))
    return sorted(notebooks)


def select_notebook_interactive(directory: Optional[Path] = None) -> Optional[Path]:
    """
    Interactive notebook selection from directory.
    
    Args:
        directory: Directory to search for notebooks
        
    Returns:
        Selected notebook path or None
    """
    # If no directory specified, use current directory
    if directory is None:
        directory = Path.cwd()
    
    notebooks = find_notebooks(directory)
    
    # If no notebooks found, ask user for different directory
    if not notebooks:
        print(f"[!] No Jupyter notebooks found in: {directory}")
        print()
        while True:
            custom_dir = input("Enter path to notebook directory (or 'q' to quit): ").strip()
            if custom_dir.lower() == 'q':
                return None
            
            custom_path = Path(custom_dir)
            if not custom_path.exists():
                print(f"[!] Directory not found: {custom_path}")
                continue
            
            notebooks = find_notebooks(custom_path)
            if notebooks:
                directory = custom_path
                break
            else:
                print(f"[!] No notebooks found in: {custom_path}")
                continue
    
    if not notebooks:
        print("[!] No notebooks found.")
        return None
    
    print("\n[*] Available Notebooks:")
    print("-" * 60)
    for i, nb in enumerate(notebooks, 1):
        try:
            relative_path = nb.relative_to(Path.cwd())
        except ValueError:
            relative_path = nb
        print(f"{i:2d}. {relative_path}")
    
    print()
    while True:
        try:
            choice = input(f"Select notebook (1-{len(notebooks)}) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(notebooks):
                return notebooks[idx]
            print(f"[!] Please enter a number between 1 and {len(notebooks)}")
        except ValueError:
            print("[!] Invalid input. Please enter a number.")


def select_mode_interactive() -> Optional[str]:
    """
    Interactive mode selection (AUDIT or CONSTRUCTION).
    
    Returns:
        Selected mode ('audit', 'construction') or None
    """
    print("\n[?] Select Analysis Mode:")
    print("-" * 60)
    print("1. AUDIT       - Review existing notebook (6-pass diagnostic)")
    print("2. CONSTRUCTION - Build new/refactor notebook (3-phase build)")
    print()
    
    while True:
        choice = input("Select mode (1 or 2) or 'q' to quit: ").strip()
        if choice == '1':
            return 'audit'
        elif choice == '2':
            return 'construction'
        elif choice.lower() == 'q':
            return None
        print("[!] Please enter 1, 2, or 'q'")


def select_audit_pass_interactive() -> Optional[int]:
    """
    Interactive audit pass selection.
    
    Returns:
        Selected pass number (1-6) or None
    """
    audit_passes = get_all_audit_passes()
    
    print("\n[+] Available Audit Passes:")
    print("-" * 60)
    for pass_num in sorted(audit_passes.keys()):
        pass_info = audit_passes[pass_num]
        print(f"Pass {pass_num}: {pass_info['name']}")
        print(f"  └─ {pass_info['description']}")
        print()
    print(" 0. ALL passes (1-6)")
    print()
    
    while True:
        try:
            choice = input(f"Select pass (0-6) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            pass_num = int(choice)
            if pass_num == 0:
                return 0
            if 1 <= pass_num <= 6:
                return pass_num
            print("[!] Please enter a number between 0 and 6")
        except ValueError:
            print("[!] Invalid input. Please enter a number.")


def select_construction_phase_interactive() -> Optional[int]:
    """
    Interactive construction phase selection.
    
    Returns:
        Selected phase number (1-3) or None
    """
    construction_phases = get_all_construction_phases()
    
    print("\n[B] Available Construction Phases:")
    print("-" * 60)
    for phase_num in sorted(construction_phases.keys()):
        phase_info = construction_phases[phase_num]
        print(f"Phase {phase_num}: {phase_info['name']}")
        print(f"  └─ {phase_info['description']}")
        print()
    print(" 0. ALL phases (1-3)")
    print()
    
    while True:
        try:
            choice = input(f"Select phase (0-3) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            phase_num = int(choice)
            if phase_num == 0:
                return 0
            if 1 <= phase_num <= 3:
                return phase_num
            print("[!] Please enter a number between 0 and 3")
        except ValueError:
            print("[!] Invalid input. Please enter a number.")


def run_audit_pass(notebook_path: Path, pass_num: int) -> None:
    """
    Run a specific audit pass and generate report.
    
    Args:
        notebook_path: Path to notebook to audit
        pass_num: Pass number (1-6)
    """
    print(f"\n[A] Running Audit Pass {pass_num}...")
    print("-" * 60)
    
    if not notebook_path.exists():
        print(f"[!] Error: Notebook not found: {notebook_path}")
        return
    
    try:
        # Run actual audit logic for mechanical passes
        if pass_num in [1, 2, 5]:
            results = run_all_mechanical_passes(notebook_path)
            if pass_num in results:
                pass_result = results[pass_num]
            else:
                print(f"[!] Error: Could not run pass {pass_num}")
                return
        else:
            # For semantic passes (3, 4, 6), show template for now
            pass_result = {
                'pass': pass_num,
                'name': get_audit_pass_corrections(pass_num).get('name', f'Pass {pass_num}'),
                'status': 'TEMPLATE',
                'issues': [],
                'risk_score': 'Moderate',
                'gate_decision': 'PROCEED_WITH_WARNINGS'
            }
        
        pass_name = pass_result.get('name', f'Pass {pass_num}')
        issues = pass_result.get('issues', [])
        risk_score = pass_result.get('risk_score', 'Moderate')
        gate_decision = pass_result.get('gate_decision', 'PROCEED')
        
        print(f"Pass Name: {pass_name}")
        print(f"Notebook: {notebook_path.name}")
        print(f"Issues Found: {len(issues)}")
        print()
        
        generator = ReportGenerator(output_dir=_get_output_dir())
        report_path = generator.generate_audit_report(
            notebook_name=notebook_path.name,
            pass_num=pass_num,
            issues=issues,
            risk_score=risk_score,
            gate_decision=gate_decision,
            additional_context={
                'notebook_path': str(notebook_path),
                'framework_version': '1.0',
                'pass_status': pass_result.get('status', 'unknown')
            }
        )
        
        print(f"[+] Report generated: {report_path.name}")
        print(f"  Location: {report_path}")
        print()
    
    except Exception as e:
        print(f"[!] Error running audit: {e}")
        import traceback
        traceback.print_exc()


def run_construction_phase(notebook_path: Path, phase_num: int) -> None:
    """
    Run a specific construction phase and generate report.
    
    Args:
        notebook_path: Path to notebook being constructed
        phase_num: Phase number (1-3)
    """
    print(f"\n[B] Running Construction Phase {phase_num}...")
    print("-" * 60)
    
    if not notebook_path.exists():
        print(f"[!] Error: Notebook not found: {notebook_path}")
        return
    
    try:
        # Run actual construction logic
        results = run_all_construction_phases(notebook_path)
        if phase_num in results:
            phase_result = results[phase_num]
        else:
            print(f"[!] Error: Could not run phase {phase_num}")
            return
        
        phase_name = phase_result.get('name', f'Phase {phase_num}')
        findings = phase_result.get('findings', [])
        gate_decision = phase_result.get('gate_decision', 'PROCEED')
        checklist = phase_result.get('checklist', {})
        
        print(f"Phase Name: {phase_name}")
        print(f"Notebook: {notebook_path.name}")
        print(f"Findings: {len(findings)}")
        print()
        
        generator = ReportGenerator(output_dir=_get_output_dir())
        report_path = generator.generate_construction_report(
            notebook_name=notebook_path.name,
            phase_num=phase_num,
            findings=findings,
            status='In Progress',
            gate_decision=gate_decision,
            additional_context=checklist
        )
        
        print(f"[+] Report generated: {report_path.name}")
        print(f"  Location: {report_path}")
        print()
    
    except Exception as e:
        print(f"[!] Error running construction phase: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Notebook Audit & Construction Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Interactive mode:
    python notebookAuditCLI.py
   
  Interactive with specific directory:
    python notebookAuditCLI.py --dir /path/to/notebooks
   
  Audit specific pass:
    python notebookAuditCLI.py --mode audit --notebook notebook.ipynb --pass 2
   
  Run all 6 audit passes:
    python notebookAuditCLI.py --mode audit --notebook notebook.ipynb --all
   
  Construction phase:
    python notebookAuditCLI.py --mode construction --notebook notebook.ipynb --phase 1
   
  Run all 3 construction phases:
    python notebookAuditCLI.py --mode construction --notebook notebook.ipynb --all
"""
    )
    
    parser.add_argument(
        '--mode',
        choices=['audit', 'construction'],
        help='Analysis mode (audit or construction)'
    )
    parser.add_argument(
        '--notebook',
        type=Path,
        help='Path to Jupyter notebook'
    )
    parser.add_argument(
        '--pass',
        type=int,
        choices=range(1, 7),
        dest='pass_num',
        help='Audit pass number (1-6, for --mode audit)'
    )
    parser.add_argument(
        '--phase',
        type=int,
        choices=range(1, 4),
        help='Construction phase number (1-3, for --mode construction)'
    )
    parser.add_argument(
        '--dir',
        type=Path,
        help='Directory to scan for notebooks (default: nbs/ subdirectory if it exists, else current directory)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all notebooks in directory and exit'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all passes/phases (overrides --pass/--phase)'
    )
    
    args = parser.parse_args()
    
    # List mode
    if args.list:
        notebooks = find_notebooks(args.dir)
        if not notebooks:
            print("No notebooks found.")
            return
        print("\n[*] Notebooks found:")
        for nb in notebooks:
            try:
                rel_path = nb.relative_to(Path.cwd())
            except ValueError:
                rel_path = nb
            print(f"  {rel_path}")
        return
    
    # Interactive mode if no arguments
    if not args.mode and not args.notebook:
        print("\n" + "=" * 60)
        print("   Notebook Audit & Construction Framework")
        print("=" * 60)
        
        mode = select_mode_interactive()
        if mode is None:
            print("[!] Goodbye!")
            return
        
        notebook = select_notebook_interactive(args.dir)
        if notebook is None:
            print("[!] Goodbye!")
            return
        
        if mode == 'audit':
            pass_num = select_audit_pass_interactive()
            if pass_num is None:
                print("[!] Goodbye!")
                return
            if pass_num == 0:
                for p in range(1, 7):
                    run_audit_pass(notebook, p)
            else:
                run_audit_pass(notebook, pass_num)
        else:  # construction
            phase_num = select_construction_phase_interactive()
            if phase_num is None:
                print("[!] Goodbye!")
                return
            if phase_num == 0:
                for p in range(1, 4):
                    run_construction_phase(notebook, p)
            else:
                run_construction_phase(notebook, phase_num)
    
    # CLI argument mode
    else:
        if not args.mode:
            print("[!] Error: --mode is required (audit or construction)")
            sys.exit(1)
        
        if not args.notebook:
            print("[!] Error: --notebook is required")
            sys.exit(1)
        
        if not args.notebook.exists():
            print(f"[!] Error: Notebook not found: {args.notebook}")
            sys.exit(1)
        
        if args.mode == 'audit':
            if args.all:
                for p in range(1, 7):
                    run_audit_pass(args.notebook, p)
            elif not args.pass_num:
                print("[!] Error: --pass or --all is required for audit mode")
                sys.exit(1)
            else:
                run_audit_pass(args.notebook, args.pass_num)
        else:  # construction
            if args.all:
                for p in range(1, 4):
                    run_construction_phase(args.notebook, p)
            elif not args.phase:
                print("[!] Error: --phase or --all is required for construction mode")
                sys.exit(1)
            else:
                run_construction_phase(args.notebook, args.phase)
    
    print("[+] Done!")


if __name__ == "__main__":
    main()
