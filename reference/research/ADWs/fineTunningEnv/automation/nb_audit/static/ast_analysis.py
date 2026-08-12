"""AST-level static checks over the notebook's module namespace.

Walks every code cell's AST (in execution order) and emits deterministic,
LLM-free findings for:

- **undefined names** — a name loaded at module scope but never bound anywhere
  in the notebook (import, assignment, def, for/with target, etc.).
- **execution order** — a name referenced in an earlier cell but first bound in
  a later cell (use-before-definition).
- **missing seed** — randomness used (``torch.randn``, ``np.random.*``,
  ``random.*``, an unseeded split, ``shuffle=True``) without any fixed seed
  (``manual_seed`` / ``random.seed`` / ``random_state=``).
- **split definitions** — a training signal (``.fit()`` / ``model.train()`` /
  ``optimizer.step()``) with no train/test/validation split defined, and split
  calls made without a ``random_state`` / seed.

The namespace analysis is module-scope only: function/class bodies are treated as
their own scope, so a name used only inside a function is not falsely flagged as
undefined at the notebook level.
"""

from __future__ import annotations

import ast
import builtins

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.static.check_registry import StaticCheck

# --------------------------------------------------------------------------- #
# Classification tables
# --------------------------------------------------------------------------- #
_SEED_CALLS = frozenset({
    "random.seed", "np.random.seed", "torch.manual_seed",
    "torch.cuda.manual_seed", "torch.cuda.manual_seed_all",
    "set_seed", "seed_everything", "tf.random.set_seed",
})

_RANDOM_CALLS = frozenset({
    "random.random", "random.rand", "random.randint", "random.randrange",
    "random.choice", "random.shuffle", "random.sample", "random.uniform",
    "random.gauss", "random.normalvariate", "random.triangular",
    "np.random.rand", "np.random.randn", "np.random.randint", "np.random.random",
    "np.random.random_sample", "np.random.choice", "np.random.shuffle",
    "np.random.permutation", "np.random.uniform", "np.random.normal",
    "torch.rand", "torch.randn", "torch.randint", "torch.randperm",
    "torch.rand_like", "torch.randn_like",
})

_SPLIT_CALLS = frozenset({
    "train_test_split", "KFold", "StratifiedKFold", "ShuffleSplit",
    "StratifiedShuffleSplit", "GroupKFold", "GroupShuffleSplit",
    "TimeSeriesSplit", "RepeatedKFold", "RepeatedStratifiedKFold",
    "LeaveOneOut", "LeavePOut", "random_split",
})

# Names provided by the notebook runtime that need no explicit binding.
_NOTEBOOK_GLOBALS = frozenset({
    "_", "__name__", "__file__", "__builtins__", "__doc__", "__package__",
    "__spec__", "__loader__", "get_ipython", "display", "In", "Out",
})

_BUILTINS = frozenset(dir(builtins)) | _NOTEBOOK_GLOBALS


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _dotted_name(node: ast.Call) -> str:
    """Return the dotted call name (``torch.randn``, ``model.fit``)."""
    parts: list[str] = []
    func: ast.expr = node.func
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _normalize(dotted: str) -> str:
    """Normalize ``numpy.*`` to ``np.*`` so classification tables stay small."""
    if dotted.startswith("numpy"):
        return "np" + dotted[len("numpy"):]
    return dotted


def _is_seed_call(dotted: str) -> bool:
    return _normalize(dotted) in _SEED_CALLS


def _is_random_call(dotted: str) -> bool:
    return _normalize(dotted) in _RANDOM_CALLS


def _is_split_call(dotted: str) -> bool:
    parts = _normalize(dotted).split(".")
    return parts[-1] in _SPLIT_CALLS


def _is_training_call(dotted: str) -> bool:
    parts = _normalize(dotted).split(".")
    last = parts[-1] if parts else ""
    if last in {"fit", "train", "backward", "step"}:
        return True
    return False


# --------------------------------------------------------------------------- #
# Namespace visitor (module scope only)
# --------------------------------------------------------------------------- #
class _NamespaceVisitor(ast.NodeVisitor):
    """Collects module-scope bound and loaded names for one cell."""

    def __init__(self, cell_index: int) -> None:
        self.cell_index = cell_index
        self.bound: list[tuple[str, int]] = []  # (name, line)
        self.used: list[tuple[str, int]] = []   # (name, line)
        self._scope = 0

    def _bind(self, name: str, lineno: int) -> None:
        if name and self._scope == 0:
            self.bound.append((name, lineno))

    def _use(self, name: str, lineno: int) -> None:
        if name and self._scope == 0:
            self.used.append((name, lineno))

    # -- bindings ---------------------------------------------------------- #
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._bind(alias.asname or alias.name.split(".")[0], node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            self._bind(alias.asname or alias.name, node.lineno)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._bind(node.name, node.lineno)
        self._visit_nested(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._bind(node.name, node.lineno)
        self._visit_nested(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name, node.lineno)
        self._visit_nested(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_nested(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind_target(target, node.lineno)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._bind_target(node.target, node.lineno)
        if node.value is not None:
            self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._use_target(node.target, node.lineno)
        self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        self._bind_target(node.target, node.lineno)
        self.visit(node.iter)
        self._visit_body(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars, node.lineno)
            self.visit(item.context_expr)
        self._visit_body(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name, node.lineno)
        if node.type is not None:
            self.visit(node.type)
        self._visit_body(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._bind_target(node.target, node.lineno)
        self.visit(node.iter)
        for cond in node.ifs:
            self.visit(cond)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._use(node.id, node.lineno)
        elif isinstance(node.ctx, ast.Store):
            self._bind(node.id, node.lineno)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self._bind(name, node.lineno)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self._bind(name, node.lineno)

    # -- helpers ----------------------------------------------------------- #
    def _visit_nested(self, node: ast.AST) -> None:
        self._scope += 1
        for child in ast.iter_child_nodes(node):
            self.visit(child)
        self._scope -= 1

    def _visit_body(self, node: ast.AST) -> None:
        for stmt in getattr(node, "body", ()):
            self.visit(stmt)
        for stmt in getattr(node, "orelse", ()):
            self.visit(stmt)

    def _bind_target(self, target: ast.expr, lineno: int) -> None:
        if isinstance(target, ast.Name):
            self._bind(target.id, lineno)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind_target(elt, lineno)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value, lineno)
        elif isinstance(target, (ast.Subscript, ast.Attribute)):
            self.visit(target.value)  # base is read (Load)

    def _use_target(self, target: ast.expr, lineno: int) -> None:
        if isinstance(target, ast.Name):
            self._use(target.id, lineno)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._use_target(elt, lineno)
        elif isinstance(target, ast.Subscript):
            self.visit(target.value)


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #
class AstAnalysisCheck(StaticCheck):
    """Namespace, execution-order, seed, and split-definition checks."""

    name = "ast_analysis"
    category = "ast_analysis"
    severity = 8

    def check(self, model: NotebookModel) -> list[Finding]:
        findings: list[Finding] = []

        # 1) module-scope namespace: bound + used names across all cells.
        first_bind: dict[str, int] = {}
        uses: list[tuple[str, int, int]] = []  # (name, cell_index, line)
        for cell in model.code_cells:
            if cell.ast is None:
                continue  # syntax errors are reported by SyntaxCheck
            visitor = _NamespaceVisitor(cell.index)
            visitor.visit(cell.ast)
            for name, _line in visitor.bound:
                first_bind.setdefault(name, cell.index)
            for name, line in visitor.used:
                uses.append((name, cell.index, line))

        # 2) undefined-name + use-before-definition findings.
        for name, cell_index, line in uses:
            if name in _BUILTINS:
                continue
            if name not in first_bind:
                findings.append(
                    self.finding(
                        location=Location(cell=_cell_id(model, cell_index), line=line),
                        issue=f"Name '{name}' is used but never defined in the notebook",
                        root_cause=(
                            f"'{name}' is referenced at module scope with no matching "
                            "import, assignment, or definition"
                        ),
                        impact="Cell raises NameError at execution time",
                        correction=f"Define or import '{name}' before using it",
                        severity=9,
                        category="undefined_name",
                    )
                )
            elif cell_index < first_bind[name]:
                findings.append(
                    self.finding(
                        location=Location(cell=_cell_id(model, cell_index), line=line),
                        issue=f"Name '{name}' is used before its first definition",
                        root_cause=(
                            f"'{name}' is first defined in cell {first_bind[name]} but "
                            f"referenced in cell {cell_index}"
                        ),
                        impact="NameError if this cell runs before the definition cell",
                        correction=f"Move the definition of '{name}' before this cell",
                        severity=8,
                        category="execution_order",
                    )
                )

        # 3) seed + split findings from a whole-notebook call scan.
        scan = _CallScan(model)
        findings.extend(self._seed_findings(model, scan))
        findings.extend(self._split_findings(model, scan))
        return findings

    def _seed_findings(self, model: NotebookModel, scan: "_CallScan") -> list[Finding]:
        if not scan.random_calls:
            return []
        if scan.seed_calls or scan.random_state_used:
            return []
        first_cell, first_line, _dotted = scan.random_calls[0]
        return [
            self.finding(
                location=Location(cell=_cell_id(model, first_cell), line=first_line),
                issue="Randomness used without a fixed seed",
                root_cause=(
                    "A randomized operation (e.g. torch.randn, np.random.*, random.*, "
                    "or an unseeded split) is present with no manual_seed / random.seed "
                    "/ random_state anywhere in the notebook"
                ),
                impact="Results are not reproducible across runs",
                correction=(
                    "Set a fixed seed (torch.manual_seed, np.random.seed, random.seed) "
                    "or pass random_state to the split/model"
                ),
                severity=8,
                category="reproducibility",
            )
        ]

    def _split_findings(self, model: NotebookModel, scan: "_CallScan") -> list[Finding]:
        findings: list[Finding] = []

        # training present but no split defined.
        if scan.training_calls and not scan.split_calls:
            cell, line, _dotted = scan.training_calls[0]
            findings.append(
                self.finding(
                    location=Location(cell=_cell_id(model, cell), line=line),
                    issue="Model training detected but no train/test/validation split is defined",
                    root_cause=(
                        "A training signal (.fit() / model.train() / optimizer.step()) "
                        "was found with no split definition (train_test_split, KFold, ...)"
                    ),
                    impact="No held-out evaluation set; results may overfit and are not comparable",
                    correction="Define an explicit train/test (and validation) split",
                    severity=7,
                    category="splits",
                )
            )

        # split without seed / random_state.
        for cell, line, dotted in scan.split_calls:
            if scan.seed_calls or scan.random_state_used:
                break
            findings.append(
                self.finding(
                    location=Location(cell=_cell_id(model, cell), line=line),
                    issue=f"Split '{dotted}' is called without random_state or a fixed seed",
                    root_cause="The split is randomized but no seed/random_state fixes it",
                    impact="Train/validation/test partitions differ between runs",
                    correction="Pass random_state (or set a global seed) for a deterministic split",
                    severity=7,
                    category="splits",
                )
            )
        return findings


def _cell_id(model: NotebookModel, cell_index: int) -> str:
    for cell in model.cells:
        if cell.index == cell_index:
            return cell.id
    return f"cell-{cell_index}"


class _CallScan:
    """Whole-notebook scan of calls (any scope) for seed/split/training signals."""

    def __init__(self, model: NotebookModel) -> None:
        self.seed_calls: list[tuple[int, int, str]] = []
        self.random_calls: list[tuple[int, int, str]] = []
        self.split_calls: list[tuple[int, int, str]] = []
        self.training_calls: list[tuple[int, int, str]] = []
        self.random_state_used = False

        for cell in model.code_cells:
            if cell.ast is None:
                continue
            for node in ast.walk(cell.ast):
                if not isinstance(node, ast.Call):
                    continue
                dotted = _dotted_name(node)
                if not dotted:
                    continue
                line = getattr(node, "lineno", None) or 0
                self._classify(cell.index, line, dotted, node)

    def _classify(self, cell: int, line: int, dotted: str, node: ast.Call) -> None:
        if _is_seed_call(dotted):
            self.seed_calls.append((cell, line, dotted))
        if any(kw.arg == "random_state" for kw in node.keywords):
            self.random_state_used = True
        if any(kw.arg == "seed" for kw in node.keywords):
            self.seed_calls.append((cell, line, dotted))
        if any(
            kw.arg == "shuffle"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        ):
            self.random_calls.append((cell, line, dotted))
        if _is_random_call(dotted):
            self.random_calls.append((cell, line, dotted))
        if _is_split_call(dotted):
            self.split_calls.append((cell, line, dotted))
        if _is_training_call(dotted):
            self.training_calls.append((cell, line, dotted))
