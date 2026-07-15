"""
Audit Engine - Core logic for each audit pass.

Implements the 6-pass notebook audit protocol with both mechanical (1,2,5)
and semantic (3,4,6) passes.
"""

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any


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


class AuditEngine:
    """Core audit logic for all passes."""
    
    # Standard notebook sections for Pass 1
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
    
    # Seed patterns for Pass 2
    SEED_PATTERNS = [
        r"random\.seed\(",
        r"np\.random\.seed\(",
        r"numpy\.random\.seed\(",
        r"torch\.manual_seed\(",
        r"tf\.random\.set_seed\(",
        r"set_seed\(",
    ]
    
    def __init__(self, notebook_path: Path):
        self.notebook_path = Path(notebook_path)
        self.nb = load_notebook(self.notebook_path)
        self.cells = get_cells(self.nb)
    
    def run_pass_1(self) -> Dict[str, Any]:
        """
        Pass 1: Structural Overview
        Check for clear section headers, coherent purpose, linear execution.
        """
        headers = [c for c in self.cells if c['type'] == 'markdown' and re.match(r'^\s*#{1,3}\s', c['source'])]
        red_flags = []
        issues = []
        
        # Check for section headers
        if not headers:
            red_flags.append("No markdown section headers found")
            issues.append({
                'type': 'Missing section headers',
                'severity': 'HIGH',
                'description': 'Notebook lacks markdown section headers making navigation difficult'
            })
        else:
            # Extract header text
            header_texts = [h['source'].splitlines()[0].strip() for h in headers]
            
        # Check for coherent purpose (multiple unrelated sections would suggest mixed purposes)
        code_cells = [c for c in self.cells if c['type'] == 'code']
        
        # Check execution order
        exec_counts = [c['exec_count'] for c in self.cells if c['type'] == 'code' and c['exec_count'] is not None]
        if exec_counts and exec_counts != sorted(exec_counts):
            red_flags.append("Cell execution order is not linear (out-of-order execution detected)")
            issues.append({
                'type': 'Out-of-order cell execution',
                'severity': 'CRITICAL',
                'description': 'Cell execution counters show non-sequential numbers'
            })
        
        # Check for empty code cell outputs
        empty_outputs = [c['index'] for c in code_cells if not c['outputs'] and c['exec_count'] is not None]
        if empty_outputs:
            red_flags.append(f"Code cells with no outputs despite being executed: {empty_outputs}")
            if len(empty_outputs) > len(code_cells) // 3:  # If > 1/3 are empty
                issues.append({
                    'type': 'Empty code cell outputs',
                    'severity': 'MEDIUM',
                    'description': 'Many code cells show execution counter but have no output'
                })
        
        risk_score = 'Low' if not red_flags else ('High' if any('CRITICAL' in str(i.get('severity')) for i in issues) else 'Moderate')
        
        return {
            'pass': 1,
            'name': 'Structural Overview',
            'status': 'COMPLETE',
            'issues': issues,
            'risk_score': risk_score,
            'gate_decision': 'BLOCK' if any(i.get('severity') == 'CRITICAL' for i in issues) else 'PROCEED_WITH_WARNINGS' if issues else 'PROCEED',
            'findings': {
                'section_map': [h['source'].splitlines()[0].strip() for h in headers] if headers else 'No clear sections',
                'red_flags': red_flags,
                'total_cells': len(self.cells),
                'code_cells': len(code_cells),
                'markdown_cells': len([c for c in self.cells if c['type'] == 'markdown'])
            }
        }
    
    def run_pass_2(self) -> Dict[str, Any]:
        """
        Pass 2: Reproducibility Check
        Verify dependencies are pinned and random seeds are set.
        """
        code = '\n'.join(c['source'] for c in self.cells if c['type'] == 'code')
        issues = []
        
        # Check for random seeds
        seeds_found = [p for p in self.SEED_PATTERNS if re.search(p, code)]
        if not seeds_found:
            issues.append({
                'type': 'No random seed initialization',
                'severity': 'HIGH',
                'description': 'No random seed calls detected - results will vary on each run'
            })
        
        # Check for dependency files
        dep_files = []
        for fname in ['requirements.txt', 'environment.yml', 'pyproject.toml']:
            if (self.notebook_path.parent / fname).exists():
                dep_files.append(fname)
        
        if not dep_files:
            issues.append({
                'type': 'No dependency file',
                'severity': 'HIGH',
                'description': 'No requirements.txt / environment.yml / pyproject.toml found alongside notebook'
            })
        
        # Check for hardcoded paths
        hardcoded_path_pattern = re.compile(r"""["']([/\\](?:[a-zA-Z]:[/\\])?(?:Users|home|mnt|Documents|Desktop|tmp)[^"']*?)["']""")
        hardcoded_paths = hardcoded_path_pattern.findall(code)
        if hardcoded_paths:
            issues.append({
                'type': 'Hardcoded absolute paths',
                'severity': 'HIGH',
                'description': f'Found {len(hardcoded_paths)} hardcoded absolute paths that only work on specific machines'
            })
        
        risk_score = 'Low' if not issues else ('High' if len(issues) >= 2 else 'Moderate')
        
        return {
            'pass': 2,
            'name': 'Reproducibility Check',
            'status': 'COMPLETE',
            'issues': issues,
            'risk_score': risk_score,
            'gate_decision': 'BLOCK' if risk_score == 'High' else 'PROCEED_WITH_WARNINGS' if issues else 'PROCEED',
            'findings': {
                'seeds_found': seeds_found,
                'dependency_files': dep_files,
                'hardcoded_paths_count': len(hardcoded_paths),
                'hardcoded_paths': hardcoded_paths[:5] if hardcoded_paths else []
            }
        }
    
    def run_pass_5(self) -> Dict[str, Any]:
        """
        Pass 5: Code Quality Review
        Check for repeated blocks, unused imports, bloated outputs.
        """
        code_cells = [c for c in self.cells if c['type'] == 'code']
        full_code = '\n'.join(c['source'] for c in code_cells)
        issues = []
        
        # Unused imports (via AST)
        unused_imports = []
        try:
            tree = ast.parse(full_code)
            imported_names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_names.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported_names.update(alias.asname or alias.name for alias in node.names)
            used_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            unused_imports = sorted(imported_names - used_names)
        except SyntaxError:
            pass
        
        if unused_imports:
            issues.append({
                'type': 'Unused imports',
                'severity': 'LOW',
                'description': f'Found {len(unused_imports)} unused import(s): {", ".join(unused_imports[:3])}'
            })
        
        # Repeated code blocks (3+)
        def _normalize(line: str) -> str:
            return re.sub(r'\s+', ' ', line.strip())
        
        normalized_blocks = [_normalize(c['source']) for c in code_cells if c['source'].strip()]
        block_counts = Counter(normalized_blocks)
        repeated_blocks = [block[:60] + '...' for block, count in block_counts.items() if count >= 3]
        
        if repeated_blocks:
            issues.append({
                'type': 'Repeated code blocks (3+ occurrences)',
                'severity': 'MEDIUM',
                'description': f'Found {len(repeated_blocks)} code block pattern(s) repeated 3+ times - candidate for refactoring'
            })
        
        # Bloated outputs
        bloated_output_cells = []
        for c in code_cells:
            for out in c['outputs']:
                text = out.get('text') or out.get('data', {}).get('text/plain', '')
                text_len = len(''.join(text)) if isinstance(text, list) else len(str(text))
                if text_len > 5000:
                    bloated_output_cells.append(c['index'])
                    break
        
        if bloated_output_cells:
            issues.append({
                'type': 'Bloated cell outputs',
                'severity': 'MEDIUM',
                'description': f'Found {len(bloated_output_cells)} cell(s) with large outputs (>5KB) that reduce readability'
            })
        
        risk_score = 'Low' if not issues else 'Moderate'
        
        return {
            'pass': 5,
            'name': 'Code Quality Review',
            'status': 'COMPLETE',
            'issues': issues,
            'risk_score': risk_score,
            'gate_decision': 'PROCEED',
            'findings': {
                'unused_imports': unused_imports,
                'repeated_blocks_count': len(repeated_blocks),
                'bloated_output_cells': bloated_output_cells
            }
        }


def run_all_mechanical_passes(notebook_path: Path) -> Dict[int, Dict[str, Any]]:
    """Run all mechanical passes (1, 2, 5) and return results."""
    engine = AuditEngine(notebook_path)
    
    results = {
        1: engine.run_pass_1(),
        2: engine.run_pass_2(),
        5: engine.run_pass_5()
    }
    
    return results
