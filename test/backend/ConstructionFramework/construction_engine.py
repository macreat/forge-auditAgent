"""
Construction Engine - Core logic for each construction phase.

Implements 3-phase notebook construction framework:
- Phase 1: Scaffold - Structure before writing
- Phase 2: Write - Fill sections with documented code  
- Phase 3: Validate - Test reproducibility
"""

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple


def load_notebook(path: Path) -> dict:
    """Load and parse a Jupyter notebook."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_cells(nb: dict) -> List[Dict[str, Any]]:
    """Extract cell information from notebook."""
    cells = []
    for i, cell in enumerate(nb.get('cells', [])):
        src = cell.get('source', '')
        text = ''.join(src) if isinstance(src, list) else src
        cells.append({
            'index': i,
            'type': cell.get('cell_type'),
            'source': text,
            'exec_count': cell.get('execution_count'),
            'outputs': cell.get('outputs', []),
        })
    return cells


class ConstructionEngine:
    """Core construction logic for all phases."""
    
    CANONICAL_SECTIONS = [
        "Environment & Dependencies",
        "Configuration & Global Parameters",
        "Data Ingestion",
        "Preprocessing & Feature Engineering",
        "Model Definition & Training",
        "Evaluation & Metrics",
        "Artifact Export",
        "Conclusions & Next Steps"
    ]
    
    def __init__(self, notebook_path: Path):
        self.notebook_path = Path(notebook_path)
        self.nb = load_notebook(self.notebook_path)
        self.cells = get_cells(self.nb)
    
    def run_phase_1(self) -> Dict[str, Any]:
        """
        Phase 1: Scaffold
        Check if notebook has proper structure, headers, and environment setup.
        """
        findings = []
        checklist = {
            'has_headers': False,
            'headers_standard': False,
            'environment_pinned': False,
            'seeds_set': False,
            'single_purpose': True
        }
        
        # Check for section headers
        headers = [c for c in self.cells if c['type'] == 'markdown' and re.match(r'^\s*#{1,3}\s', c['source'])]
        if headers:
            checklist['has_headers'] = True
            header_texts = [h['source'].splitlines()[0].strip().lower() for h in headers]
            canonical_lower = [s.lower() for s in self.CANONICAL_SECTIONS]
            if any(canon in ' '.join(header_texts) for canon in canonical_lower):
                checklist['headers_standard'] = True
        else:
            findings.append({
                'type': 'Missing standard section headers',
                'severity': 'HIGH',
                'description': 'Add markdown cells with standard section headers before writing code'
            })
        
        # Check for dependency pinning in first cell
        code_cells = [c for c in self.cells if c['type'] == 'code']
        if code_cells:
            first_code = code_cells[0]['source'].lower()
            if 'requirements' in first_code or 'pip install' in first_code or 'conda' in first_code:
                checklist['environment_pinned'] = True
            else:
                findings.append({
                    'type': 'Environment not pinned at start',
                    'severity': 'HIGH',
                    'description': 'Add requirements.txt or environment.yml cell in Environment & Dependencies section'
                })
        
        # Check for random seeds
        code = '\n'.join(c['source'] for c in code_cells)
        seed_patterns = [r"random\.seed", r"np\.random\.seed", r"torch\.manual_seed"]
        if any(re.search(p, code) for p in seed_patterns):
            checklist['seeds_set'] = True
        else:
            findings.append({
                'type': 'Random seeds not initialized',
                'severity': 'MEDIUM',
                'description': 'Set all random seeds in Configuration section for reproducibility'
            })
        
        gate_decision = 'BLOCK' if not checklist['has_headers'] else 'PROCEED_WITH_WARNINGS' if findings else 'PROCEED'
        
        return {
            'phase': 1,
            'name': 'Scaffold (Phase 1)',
            'status': 'COMPLETE',
            'findings': findings,
            'gate_decision': gate_decision,
            'checklist': checklist,
            'recommended_sections': self.CANONICAL_SECTIONS if not headers else None
        }
    
    def run_phase_2(self) -> Dict[str, Any]:
        """
        Phase 2: Write
        Check code is well-documented, organized, and avoids repetition.
        """
        findings = []
        checklist = {
            'cells_documented': False,
            'code_not_repetitive': False,
            'variables_explicit': False,
            'sections_ordered': False
        }
        
        code_cells = [c for c in self.cells if c['type'] == 'code']
        markdown_cells = [c for c in self.cells if c['type'] == 'markdown']
        
        # Check if most code cells have preceding markdown explanation
        if len(markdown_cells) > len(code_cells) * 0.5:
            checklist['cells_documented'] = True
        else:
            findings.append({
                'type': 'Code cells lack explanatory markdown',
                'severity': 'MEDIUM',
                'description': 'Add markdown cells explaining the purpose of code blocks'
            })
        
        # Check for repeated code patterns
        normalized_codes = []
        for c in code_cells:
            normalized = re.sub(r'\s+', ' ', c['source'].strip())
            normalized_codes.append(normalized)
        
        from collections import Counter
        code_counts = Counter(normalized_codes)
        repeated = [code for code, count in code_counts.items() if count >= 3]
        
        if not repeated:
            checklist['code_not_repetitive'] = True
        else:
            findings.append({
                'type': 'Repeated code patterns (3+ times)',
                'severity': 'MEDIUM',
                'description': f'Found {len(repeated)} code pattern(s) repeated 3+ times - refactor into functions'
            })
        
        # Check if variables are passed explicitly between cells
        # This is a heuristic - we're looking for function definitions
        all_code = '\n'.join(c['source'] for c in code_cells)
        if 'def ' in all_code:
            checklist['variables_explicit'] = True
        else:
            findings.append({
                'type': 'Variables may be passed implicitly',
                'severity': 'LOW',
                'description': 'Consider using functions to pass variables explicitly between cells'
            })
        
        # Check section ordering
        headers = [c['source'].splitlines()[0].strip() for c in self.cells if c['type'] == 'markdown' and re.match(r'^\s*#{1,3}\s', c['source'])]
        if len(headers) > 1:
            checklist['sections_ordered'] = True
        
        gate_decision = 'PROCEED_WITH_WARNINGS' if findings else 'PROCEED'
        
        return {
            'phase': 2,
            'name': 'Write (Phase 2)',
            'status': 'COMPLETE',
            'findings': findings,
            'gate_decision': gate_decision,
            'checklist': checklist
        }
    
    def run_phase_3(self) -> Dict[str, Any]:
        """
        Phase 3: Validate
        Check reproducibility, idempotency, and artifact versioning.
        """
        findings = []
        checklist = {
            'idempotent_cells': False,
            'artifacts_versioned': False,
            'reproducible': False,
            'dependencies_complete': False
        }
        
        code_cells = [c for c in self.cells if c['type'] == 'code']
        code = '\n'.join(c['source'] for c in code_cells)
        
        # Check for idempotent patterns
        if 'if not Path' in code or 'if not os.path.exists' in code or 'if not file_path.exists' in code:
            checklist['idempotent_cells'] = True
        else:
            findings.append({
                'type': 'Cells may not be idempotent',
                'severity': 'MEDIUM',
                'description': 'Add checks before file operations to ensure cells can run multiple times safely'
            })
        
        # Check for artifact versioning
        if 'timestamp' in code or 'datetime' in code or '.strftime' in code:
            checklist['artifacts_versioned'] = True
        else:
            findings.append({
                'type': 'Artifacts not versioned',
                'severity': 'HIGH',
                'description': 'Add timestamp-based versioning for saved models, plots, and reports'
            })
        
        # Check reproducibility
        seed_patterns = [r"random\.seed", r"np\.random\.seed", r"torch\.manual_seed"]
        if any(re.search(p, code) for p in seed_patterns):
            checklist['reproducible'] = True
        else:
            findings.append({
                'type': 'Not reproducible - no random seeds',
                'severity': 'HIGH',
                'description': 'Set all random seeds for reproducible results'
            })
        
        # Check dependency files
        dep_exists = any((self.notebook_path.parent / f).exists() for f in ['requirements.txt', 'environment.yml', 'pyproject.toml'])
        if dep_exists:
            checklist['dependencies_complete'] = True
        else:
            findings.append({
                'type': 'Dependency file missing',
                'severity': 'HIGH',
                'description': 'Create requirements.txt or environment.yml with pinned versions'
            })
        
        gate_decision = 'BLOCK' if any(f['severity'] == 'HIGH' for f in findings) else 'PROCEED_WITH_WARNINGS' if findings else 'PROCEED'
        
        return {
            'phase': 3,
            'name': 'Validate (Phase 3)',
            'status': 'COMPLETE',
            'findings': findings,
            'gate_decision': gate_decision,
            'checklist': checklist
        }


def run_all_construction_phases(notebook_path: Path) -> Dict[int, Dict[str, Any]]:
    """Run all construction phases and return results."""
    engine = ConstructionEngine(notebook_path)
    
    results = {
        1: engine.run_phase_1(),
        2: engine.run_phase_2(),
        3: engine.run_phase_3()
    }
    
    return results
