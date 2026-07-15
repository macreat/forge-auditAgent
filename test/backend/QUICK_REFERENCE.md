# Quick Reference - CLI Commands

## Interactive Mode (Recommended for First-Time Use)

```bash
cd reference/scripts

# Option 1: Start normally (will prompt for directory if none found)
python notebookAuditCLI.py

# Option 2: Specify directory to skip the prompt
python notebookAuditCLI.py --dir ..
# or
python notebookAuditCLI.py --dir /path/to/your/notebooks
```

This launches an interactive menu where you can:
1. Select **AUDIT** or **CONSTRUCTION** mode
2. Choose a notebook from the directory (or enter custom path if none found)
3. Pick a specific pass (1-6) or phase (1-3)
4. Get a detailed markdown report

---

## Command-Line Mode (Scripting & Automation)

### Audit Specific Passes

```bash
# Pass 1: Structural Overview
python notebookAuditCLI.py --mode audit --notebook notebook.ipynb --pass 1

# Pass 2: Reproducibility Check
python notebookAuditCLI.py --mode audit --notebook notebook.ipynb --pass 2

# Pass 5: Code Quality Review
python notebookAuditCLI.py --mode audit --notebook notebook.ipynb --pass 5

# Pass 3, 4, 6: Semantic passes (template-ready for LLM)
python notebookAuditCLI.py --mode audit --notebook notebook.ipynb --pass 3
```

### Construction Phases

```bash
# Phase 1: Scaffold (Structure Setup)
python notebookAuditCLI.py --mode construction --notebook notebook.ipynb --phase 1

# Phase 2: Write (Code Organization)
python notebookAuditCLI.py --mode construction --notebook notebook.ipynb --phase 2

# Phase 3: Validate (Reproducibility Check)
python notebookAuditCLI.py --mode construction --notebook notebook.ipynb --phase 3
```

### Directory Operations

```bash
# List all notebooks in current directory
python notebookAuditCLI.py --list

# List notebooks in specific directory
python notebookAuditCLI.py --dir /path/to/notebooks --list

# Scan subdirectories
python notebookAuditCLI.py --dir ~/projects --list
```

---

## Batch Processing

### Audit All Passes for One Notebook

```bash
for pass in 1 2 3 4 5 6; do
  python notebookAuditCLI.py --mode audit --notebook research.ipynb --pass $pass
done
```

### All Construction Phases for One Notebook

```bash
for phase in 1 2 3; do
  python notebookAuditCLI.py --mode construction --notebook model.ipynb --phase $phase
done
```

### Audit Multiple Notebooks

```bash
for notebook in *.ipynb; do
  echo "Auditing $notebook..."
  python notebookAuditCLI.py --mode audit --notebook "$notebook" --pass 1
  python notebookAuditCLI.py --mode audit --notebook "$notebook" --pass 2
done
```

---

## Help & Information

```bash
# Show CLI help
python notebookAuditCLI.py --help

# Show all available notebooks
python notebookAuditCLI.py --list

# Show notebooks with file sizes
python notebookAuditCLI.py --list --dir .
```

---

## Output Files

Reports are saved with timestamps for easy organization:

```
audit_report_notebook_pass1_20250115_143022.md      # Pass 1 results
audit_report_notebook_pass2_20250115_143050.md      # Pass 2 results
construction_report_notebook_phase1_20250115_144100.md  # Phase 1 results
```

---

## Python API Usage

### Audit Engine

```python
from pathlib import Path
from audit_engine import AuditEngine

# Create engine
engine = AuditEngine(Path("notebook.ipynb"))

# Run specific pass
results = engine.run_pass_1()  # Structural Overview
print(results['issues'])       # List of issues found
print(results['risk_score'])   # Risk level

# Or
results = engine.run_pass_2()  # Reproducibility
results = engine.run_pass_5()  # Code Quality
```

### Construction Engine

```python
from pathlib import Path
from construction_engine import ConstructionEngine

# Create engine
engine = ConstructionEngine(Path("notebook.ipynb"))

# Run specific phase
phase1 = engine.run_phase_1()  # Scaffold
print(phase1['findings'])      # List of findings
print(phase1['checklist'])     # Checklist status

# Or
phase2 = engine.run_phase_2()  # Write
phase3 = engine.run_phase_3()  # Validate
```

### Report Generation

```python
from pathlib import Path
from report_generator import ReportGenerator

# Create generator
generator = ReportGenerator(output_dir=Path.cwd())

# Generate audit report
report_path = generator.generate_audit_report(
    notebook_name="notebook.ipynb",
    pass_num=1,
    issues=[...],
    risk_score="High",
    gate_decision="PROCEED_WITH_WARNINGS"
)
print(f"Report saved to: {report_path}")

# Or construction report
report_path = generator.generate_construction_report(
    notebook_name="notebook.ipynb",
    phase_num=1,
    findings=[...],
    gate_decision="PROCEED"
)
```

---

## Typical Workflows

### Workflow 1: Quick Audit

```bash
# Check structure and reproducibility
python notebookAuditCLI.py --mode audit --notebook mynotebook.ipynb --pass 1
python notebookAuditCLI.py --mode audit --notebook mynotebook.ipynb --pass 2

# Review the markdown reports
cat audit_report_mynotebook_pass1_*.md
cat audit_report_mynotebook_pass2_*.md
```

### Workflow 2: Construction Review

```bash
# Build phases
python notebookAuditCLI.py --mode construction --notebook newnotebook.ipynb --phase 1
# Fix structure issues
python notebookAuditCLI.py --mode construction --notebook newnotebook.ipynb --phase 2
# Fix code issues
python notebookAuditCLI.py --mode construction --notebook newnotebook.ipynb --phase 3
# Verify reproducibility
```

### Workflow 3: Full Audit Before Publication

```bash
# Run all passes
for pass in 1 2 3 4 5 6; do
  python notebookAuditCLI.py --mode audit --notebook publish.ipynb --pass $pass
done

# Review all reports
ls -lt audit_report_publish_*.md | head -6
```

---

## Tips & Tricks

### Create a Shell Script for Batch Audits

```bash
#!/bin/bash
# audit_all.sh - Audit all notebooks in directory

for notebook in *.ipynb; do
  echo "=========================================="
  echo "Auditing: $notebook"
  echo "=========================================="
  
  for pass in 1 2; do
    python notebookAuditCLI.py --mode audit --notebook "$notebook" --pass $pass
  done
  echo ""
done
```

### Find Reports Generated Today

```bash
# Linux/Mac
find . -name "*_report_*.md" -mtime -1

# Windows PowerShell
Get-ChildItem -Filter "*_report_*.md" -File | Where-Object {$_.LastWriteTime -gt (Get-Date).AddDays(-1)}
```

### Count Issues in Reports

```bash
# Count all issues
grep -h "^\[.*\]" audit_report_*.md | wc -l

# Count by severity
grep -h "CRITICAL" audit_report_*.md | wc -l
grep -h "HIGH" audit_report_*.md | wc -l
```

---

## Common Issues & Solutions

**Q: "Notebook not found" error**
A: Make sure the path is correct. Use `python notebookAuditCLI.py --list` to find available notebooks.

**Q: Unicode encoding errors on Windows?**
A: The CLI handles Unicode. If you see errors, try: `chcp 65001` to switch to UTF-8 mode.

**Q: No reports generated?**
A: Check the notebook is valid JSON. Try: `python -m json.tool notebook.ipynb > /dev/null`

**Q: Want to run silently?**
A: Redirect output: `python notebookAuditCLI.py ... > /dev/null 2>&1`

---

**For more detailed documentation, see `reference/README.md`**

