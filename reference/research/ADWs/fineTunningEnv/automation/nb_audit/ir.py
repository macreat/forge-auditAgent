"""Intermediate representation (IR) for parsed notebooks.

:class:`NotebookParser` loads a notebook via ``nbformat`` and populates a frozen
:class:`NotebookModel` with the raw cells plus semantic sections (imports,
functions, variables, datasets, splits, models, optimizers, schedulers, metrics,
plots, artifacts, configuration, experiment variants).

The parser is pure: no LLM and no execution. Invalid notebook input raises
:class:`NotebookParseError`; callers convert that into a severity-10 Finding.
Per-cell syntax errors are NOT raised here — the cell keeps ``ast=None`` and the
static audit engine (a later slice) reports them as findings.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Mapping

try:
    import nbformat
except ImportError:  # pragma: no cover - nbformat is a runtime dependency
    nbformat = None


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class NotebookParseError(Exception):
    """Raised when a notebook cannot be parsed into an IR."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# --------------------------------------------------------------------------- #
# IR element dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CellRef:
    """One notebook cell and (for code cells) its parsed AST."""

    id: str
    index: int
    cell_type: str  # "code" | "markdown" | "raw"
    source: str
    exec_count: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    ast: Any = None  # ast.Module | None — parsed AST for code cells


@dataclass(frozen=True)
class ImportDecl:
    name: str
    alias: str | None = None
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class FuncDecl:
    name: str
    params: tuple[str, ...] = ()
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class VarDecl:
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class DatasetRef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class SplitDef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class ModelRef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class OptimizerRef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class SchedulerRef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class MetricDef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class PlotRef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class ArtifactRef:
    id: str
    name: str
    path: str = ""
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


@dataclass(frozen=True)
class VariantDef:
    id: str
    name: str
    cell_id: str = ""
    cell_index: int = -1
    line: int | None = None


# --------------------------------------------------------------------------- #
# NotebookModel
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NotebookModel:
    """Frozen IR for a notebook: cells plus semantic sections.

    ``configuration`` is the one mutable field (a dict of literal config blocks);
    the rest are tuples so patches must produce a NEW model rather than mutate.
    """

    cells: tuple[CellRef, ...] = ()
    imports: tuple[ImportDecl, ...] = ()
    functions: tuple[FuncDecl, ...] = ()
    variables: tuple[VarDecl, ...] = ()
    datasets: tuple[DatasetRef, ...] = ()
    splits: tuple[SplitDef, ...] = ()
    models: tuple[ModelRef, ...] = ()
    optimizers: tuple[OptimizerRef, ...] = ()
    schedulers: tuple[SchedulerRef, ...] = ()
    metrics: tuple[MetricDef, ...] = ()
    plots: tuple[PlotRef, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    configuration: dict = field(default_factory=dict)
    experiment_variants: tuple[VariantDef, ...] = ()

    @property
    def code_cells(self) -> tuple[CellRef, ...]:
        return tuple(c for c in self.cells if c.cell_type == "code")

    def get_cell(self, cell_id: str) -> CellRef | None:
        for cell in self.cells:
            if cell.id == cell_id:
                return cell
        return None

    def to_notebook(self) -> Any:
        """Reconstruct an nbformat notebook node from this IR.

        The controller uses this to hand a (possibly patched) IR back to the
        notebook executor. Cell ids, types, sources, metadata and execution
        counts are preserved; cell outputs are dropped (the audit never trusts
        notebook outputs as source of truth). Returns an ``nbformat.NotebookNode``
        (a ``dict`` subclass), so it serializes via the notebook manager.
        """
        if nbformat is None:
            raise NotebookParseError("nbformat is not installed")
        nb = nbformat.v4.new_notebook()
        cells = []
        for cell in self.cells:
            if cell.cell_type == "markdown":
                node = nbformat.v4.new_markdown_cell(cell.source)
            elif cell.cell_type == "raw":
                node = nbformat.v4.new_raw_cell(cell.source)
            else:
                node = nbformat.v4.new_code_cell(cell.source)
            node["id"] = cell.id
            node["metadata"] = dict(cell.metadata)
            if cell.exec_count is not None:
                node["execution_count"] = cell.exec_count
            cells.append(node)
        nb["cells"] = cells
        return nb


# --------------------------------------------------------------------------- #
# Call-name classification tables
# --------------------------------------------------------------------------- #
_DATASET_LOADERS = frozenset({
    "read_csv", "read_table", "read_parquet", "read_json", "read_pickle",
    "read_excel", "read_feather", "read_hdf", "read_sql", "read_fwf",
    "read_html", "read_sas", "read_stata", "read_orc",
    "loadtxt", "genfromtxt", "fromfile",
    "DataFrame", "TensorDataset", "DataLoader", "ImageFolder", "DatasetFolder",
    "load_dataset", "load_from_disk",
})

_SKLEARN_LOADERS = frozenset({
    "load_iris", "load_digits", "load_wine", "load_breast_cancer",
    "load_diabetes", "load_linnerud", "load_boston",
    "load_files", "load_svmlight_file", "load_svmlight_files",
    "load_sample_image", "load_sample_images",
    "fetch_20newsgroups", "fetch_california_housing", "fetch_covtype",
    "fetch_kddcup99", "fetch_lfw_people", "fetch_lfw_pairs",
    "fetch_olivetti_faces", "fetch_openml", "fetch_rcv1",
    "fetch_species_distributions",
})

_SYNTHETIC_GENERATORS = frozenset({
    "make_classification", "make_regression", "make_blobs",
    "make_moons", "make_circles", "make_hastie_10_2",
    "make_multilabel_classification", "make_friedman1", "make_friedman2",
    "make_friedman3", "make_gaussian_quantiles", "make_swiss_roll",
    "make_s_curve", "make_checkerboard", "make_biclusters",
})

_SPLIT_NAMES = frozenset({
    "train_test_split", "random_split", "ShuffleSplit", "StratifiedShuffleSplit",
    "KFold", "StratifiedKFold", "GroupKFold", "GroupShuffleSplit",
    "TimeSeriesSplit", "LeaveOneOut", "LeavePOut", "RepeatedKFold",
    "RepeatedStratifiedKFold", "PredefinedSplit",
})

_MODEL_NAMES = frozenset({
    # sklearn estimators
    "LogisticRegression", "LinearRegression", "Ridge", "Lasso", "ElasticNet",
    "RidgeClassifier", "LassoLars", "BayesianRidge", "ARDRegression",
    "SVC", "SVR", "LinearSVC", "LinearSVR", "NuSVC", "NuSVR", "OneClassSVM",
    "RandomForestClassifier", "RandomForestRegressor",
    "GradientBoostingClassifier", "GradientBoostingRegressor",
    "ExtraTreesClassifier", "ExtraTreesRegressor",
    "AdaBoostClassifier", "AdaBoostRegressor",
    "BaggingClassifier", "BaggingRegressor",
    "DecisionTreeClassifier", "DecisionTreeRegressor",
    "KNeighborsClassifier", "KNeighborsRegressor",
    "KMeans", "MiniBatchKMeans", "DBSCAN", "AgglomerativeClustering",
    "Birch", "SpectralClustering", "MeanShift", "AffinityPropagation",
    "GaussianNB", "MultinomialNB", "BernoulliNB", "ComplementNB",
    "MLPClassifier", "MLPRegressor",
    "SGDClassifier", "SGDRegressor", "Perceptron",
    "XGBClassifier", "XGBRegressor", "LGBMClassifier", "LGBMRegressor",
    "Sequential",  # torch.nn.Sequential container
})

_MODEL_ZOO_NAMES = frozenset({
    "resnet18", "resnet34", "resnet50", "resnet101", "resnet152",
    "alexnet", "vgg11", "vgg13", "vgg16", "vgg19",
    "densenet121", "densenet161", "densenet169", "densenet201",
    "inception_v3", "googlenet", "mobilenet_v2", "mobilenet_v3_large",
    "mobilenet_v3_small", "efficientnet_b0", "efficientnet_b7",
    "squeezenet1_0", "squeezenet1_1", "shufflenet_v2_x1_0",
    "resnext50_32x4d", "resnext101_32x8d", "wide_resnet50_2",
    "convnext_tiny", "convnext_small", "convnext_base", "convnext_large",
    "vit_b_16", "vit_b_32", "vit_l_16", "vit_l_32",
    "swin_t", "swin_s", "swin_b",
})

_OPTIMIZER_NAMES = frozenset({
    "Adam", "AdamW", "SGD", "RMSprop", "Adagrad", "Adadelta", "Adamax",
    "NAdam", "RAdam", "LBFGS", "ASGD", "SparseAdam", "Rprop",
})

_SCHEDULER_NAMES = frozenset({
    "StepLR", "MultiStepLR", "ExponentialLR", "CosineAnnealingLR",
    "CosineAnnealingWarmRestarts", "ReduceLROnPlateau", "LambdaLR",
    "OneCycleLR", "CyclicLR", "LinearLR", "PolynomialLR", "SequentialLR",
    "ConstantLR", "ChainedScheduler",
})

_METRIC_NAMES = frozenset({
    "accuracy_score", "f1_score", "fbeta_score", "precision_score",
    "recall_score", "precision_recall_fscore_support", "confusion_matrix",
    "classification_report", "roc_auc_score", "roc_curve",
    "mean_squared_error", "mean_absolute_error", "r2_score",
    "mean_squared_log_error", "log_loss", "hamming_loss", "jaccard_score",
    "matthews_corrcoef", "average_precision_score", "precision_recall_curve",
    "balanced_accuracy_score", "top_k_accuracy_score",
})

_PLOT_BASES = frozenset({"plt", "sns", "seaborn", "matplotlib", "matplotlib.pyplot"})

_ARTIFACT_WRITERS = frozenset({
    "save", "savefig", "savetxt", "savez", "savez_compressed", "dump",
    "to_csv", "to_json", "to_parquet", "to_pickle", "to_excel",
    "to_feather", "to_hdf", "to_html", "to_markdown", "to_latex",
})

_CONFIG_NAME_HINTS = ("config", "cfg", "param", "arg", "hyper", "hparams", "setting")
_VARIANT_NAME_HINTS = ("variant", "experiment", "run", "grid", "comb", "sweep")

_ARTIFACT_PATH_KEYWORDS = ("path", "fname", "filename", "filepath", "file", "f")


# --------------------------------------------------------------------------- #
# AST helpers
# --------------------------------------------------------------------------- #
def _call_dotted_name(node: ast.Call) -> str:
    """Return the dotted call name (``pd.read_csv``, ``torch.optim.Adam``)."""
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


def _base_and_last(dotted: str) -> tuple[str, str]:
    parts = dotted.split(".")
    return parts[0], parts[-1]


def _matches_hint(name: str, hints: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(h in low for h in hints)


def _safe_literal(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def _extract_path(node: ast.Call) -> str:
    """Best-effort extraction of an output path from a write call.

    Scans positional args in order (e.g. ``torch.save(obj, "model.pt")`` keeps
    the path in the second slot), then falls back to named path keywords.
    """
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for kw in node.keywords:
        if kw.arg in _ARTIFACT_PATH_KEYWORDS:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return ""


def _is_dataset_call(base: str, last: str, dotted: str) -> bool:
    if last in _DATASET_LOADERS:
        if last in {"loadtxt", "genfromtxt", "fromfile"}:
            return base in {"np", "numpy"}
        return True
    if last in _SKLEARN_LOADERS or last in _SYNTHETIC_GENERATORS:
        return True
    if base in {"datasets", "torchvision.datasets"}:
        return True
    if dotted.startswith(("torchvision.datasets.", "datasets.")):
        return True
    return False


def _is_split_call(base: str, last: str, dotted: str) -> bool:
    return last in _SPLIT_NAMES


def _is_model_call(base: str, last: str, dotted: str) -> bool:
    if last in _MODEL_NAMES or last in _MODEL_ZOO_NAMES:
        return True
    if dotted.startswith("torchvision.models."):
        return True
    if last.endswith("Net") or last.endswith("Model"):
        return True  # custom nn.Module subclass instantiation
    return False


def _is_plot_call(base: str, last: str, dotted: str) -> bool:
    if base in _PLOT_BASES:
        return True
    if last == "plot":
        return True  # pandas/series .plot()
    return False


def _is_artifact_call(base: str, last: str, dotted: str) -> bool:
    return last in _ARTIFACT_WRITERS


# --------------------------------------------------------------------------- #
# Accumulator + AST visitor
# --------------------------------------------------------------------------- #
class _Accumulator:
    def __init__(self) -> None:
        self.imports: list[ImportDecl] = []
        self.functions: list[FuncDecl] = []
        self.variables: list[VarDecl] = []
        self.datasets: list[DatasetRef] = []
        self.splits: list[SplitDef] = []
        self.models: list[ModelRef] = []
        self.optimizers: list[OptimizerRef] = []
        self.schedulers: list[SchedulerRef] = []
        self.metrics: list[MetricDef] = []
        self.plots: list[PlotRef] = []
        self.artifacts: list[ArtifactRef] = []
        self.variants: list[VariantDef] = []
        self.configuration: dict[str, Any] = {}


class _Analyzer(ast.NodeVisitor):
    """Walks one code cell's AST and appends discovered IR elements."""

    def __init__(
        self,
        cell_id: str,
        cell_index: int,
        acc: _Accumulator,
        counters: dict[str, int],
    ) -> None:
        self.cell_id = cell_id
        self.cell_index = cell_index
        self.acc = acc
        self.counters = counters

    def _next_id(self, kind: str) -> str:
        self.counters[kind] = self.counters.get(kind, 0) + 1
        return f"{kind}-{self.counters[kind]}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.acc.imports.append(
                ImportDecl(
                    name=alias.name,
                    alias=alias.asname,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for alias in node.names:
            name = f"{mod}.{alias.name}" if mod else alias.name
            self.acc.imports.append(
                ImportDecl(
                    name=name,
                    alias=alias.asname,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.acc.functions.append(
            FuncDecl(
                name=node.name,
                params=tuple(a.arg for a in node.args.args),
                cell_id=self.cell_id,
                cell_index=self.cell_index,
                line=node.lineno,
            )
        )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> None:
        self._handle_assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            self.acc.variables.append(
                VarDecl(
                    name=node.target.id,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._handle_call(node)
        self.generic_visit(node)

    # -- per-node handling ------------------------------------------------ #
    def _handle_assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.acc.variables.append(
                    VarDecl(
                        name=target.id,
                        cell_id=self.cell_id,
                        cell_index=self.cell_index,
                        line=node.lineno,
                    )
                )
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if _matches_hint(name, _CONFIG_NAME_HINTS):
                value = _safe_literal(node.value)
                if isinstance(value, dict):
                    self.acc.configuration[name] = value
            if _matches_hint(name, _VARIANT_NAME_HINTS):
                value = _safe_literal(node.value)
                if isinstance(value, (list, dict)):
                    self.acc.variants.append(
                        VariantDef(
                            id=self._next_id("variant"),
                            name=name,
                            cell_id=self.cell_id,
                            cell_index=self.cell_index,
                            line=node.lineno,
                        )
                    )

    def _handle_call(self, node: ast.Call) -> None:
        dotted = _call_dotted_name(node)
        if not dotted:
            return
        base, last = _base_and_last(dotted)
        line = node.lineno

        if _is_dataset_call(base, last, dotted):
            self.acc.datasets.append(
                DatasetRef(
                    id=self._next_id("dataset"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if _is_split_call(base, last, dotted):
            self.acc.splits.append(
                SplitDef(
                    id=self._next_id("split"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if _is_model_call(base, last, dotted):
            self.acc.models.append(
                ModelRef(
                    id=self._next_id("model"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if last in _OPTIMIZER_NAMES:
            self.acc.optimizers.append(
                OptimizerRef(
                    id=self._next_id("optimizer"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if last in _SCHEDULER_NAMES:
            self.acc.schedulers.append(
                SchedulerRef(
                    id=self._next_id("scheduler"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if last in _METRIC_NAMES:
            self.acc.metrics.append(
                MetricDef(
                    id=self._next_id("metric"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if _is_plot_call(base, last, dotted):
            self.acc.plots.append(
                PlotRef(
                    id=self._next_id("plot"),
                    name=dotted,
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )
        if _is_artifact_call(base, last, dotted):
            self.acc.artifacts.append(
                ArtifactRef(
                    id=self._next_id("artifact"),
                    name=dotted,
                    path=_extract_path(node),
                    cell_id=self.cell_id,
                    cell_index=self.cell_index,
                    line=line,
                )
            )


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
class NotebookParser:
    """Parses a notebook (nbformat) into a frozen :class:`NotebookModel`."""

    def parse(self, raw: str) -> NotebookModel:
        """Parse a notebook from its JSON string."""
        if nbformat is None:
            raise NotebookParseError("nbformat is not installed")
        try:
            notebook = nbformat.reads(raw, as_version=4)
        except Exception as exc:  # NotJSONError / ValidationError / JSONDecodeError
            raise NotebookParseError(
                f"Invalid notebook: {exc}", cause=exc
            ) from exc
        return self._build(notebook)

    def parse_file(self, path: str) -> NotebookModel:
        """Parse a notebook from a filesystem path."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            raise NotebookParseError(
                f"Cannot read notebook {path!r}: {exc}", cause=exc
            ) from exc
        return self.parse(raw)

    # -- internals --------------------------------------------------------- #
    def _build(self, notebook: Any) -> NotebookModel:
        cells_raw = notebook.get("cells") if isinstance(notebook, Mapping) else None
        if cells_raw is None:
            raise NotebookParseError("Notebook has no 'cells' field")

        acc = _Accumulator()
        counters: dict[str, int] = {}
        cells: list[CellRef] = []

        for index, cell in enumerate(cells_raw):
            if not isinstance(cell, Mapping):
                continue
            cell_type = cell.get("cell_type", "code")
            source = cell.get("source", "") or ""
            if isinstance(source, (list, tuple)):
                source = "".join(str(line) for line in source)
            exec_count = cell.get("execution_count")
            if exec_count is None or exec_count == "":
                exec_count = None
            else:
                exec_count = int(exec_count)
            metadata = dict(cell.get("metadata") or {})
            cell_id = str(cell.get("id") or f"cell-{index}")

            module = None
            if cell_type == "code":
                try:
                    module = ast.parse(source)
                except (SyntaxError, ValueError):
                    module = None

            cells.append(
                CellRef(
                    id=cell_id,
                    index=index,
                    cell_type=cell_type,
                    source=source,
                    exec_count=exec_count,
                    metadata=metadata,
                    ast=module,
                )
            )

            if module is not None:
                _Analyzer(cell_id, index, acc, counters).visit(module)

        return NotebookModel(
            cells=tuple(cells),
            imports=tuple(acc.imports),
            functions=tuple(acc.functions),
            variables=tuple(acc.variables),
            datasets=tuple(acc.datasets),
            splits=tuple(acc.splits),
            models=tuple(acc.models),
            optimizers=tuple(acc.optimizers),
            schedulers=tuple(acc.schedulers),
            metrics=tuple(acc.metrics),
            plots=tuple(acc.plots),
            artifacts=tuple(acc.artifacts),
            configuration=dict(acc.configuration),
            experiment_variants=tuple(acc.variants),
        )
