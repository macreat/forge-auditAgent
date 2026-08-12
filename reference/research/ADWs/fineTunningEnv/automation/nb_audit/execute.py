"""Notebook execution wrapper around :mod:`nbclient`.

:class:`NotebookExecutor` runs a notebook in a fresh ipykernel process and
returns an :class:`ExecutionResult`: the execution status plus the captured
kernel namespace (for the runtime ML QA layer) and — on any failure — a
severity-10 ``execution`` finding.

**Execution model (best-effort, sandboxed-by-convention — NOT a security
sandbox)**. ``allow_network: false`` is enforced through three cooperating
mechanisms, none of which is a real isolation boundary:

1. **Environment** — the kernel process is launched with ``IPY_ALLOW_NETWORK=0``
   and ``NB_AUDIT_ALLOW_NETWORK=0`` in its environment.
2. **Run-dir isolation** — the kernel's working directory is a dedicated run
   directory (e.g. ``audit-runs/<ts>/artifacts/``), so relative artifact paths
   never collide with the user's working tree.
3. **Kernel restart** — a brand-new kernel is started for every call to
   :meth:`NotebookExecutor.execute`, so no state leaks between runs.

A malicious notebook can still read the host filesystem or open sockets under
the same UID. This is a data-integrity tool, not a sandbox; see spec §24.

**Hang safety (mandatory)** — a kernel hang or runaway cell must never hang the
pipeline. Every code cell is bounded by a per-cell timeout (nbclient's
``timeout`` trait, from ``execution.timeout_seconds``) with
``interrupt_on_timeout`` enabled, and the whole notebook is additionally bounded
by a total wall-clock budget of ``timeout * (n_code_cells + 1)`` seconds. A cell
containing ``while True: pass`` is interrupted by the per-cell timeout and
surfaces as a severity-10 ``execution`` finding (threat-matrix RED case).
"""

from __future__ import annotations

import asyncio
import copy
import os
import pickle
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError, DeadKernelError

from nb_audit.config import AuditConfig
from nb_audit.models import Classification, Finding, Location, Status

# -- execution status values (uppercase, matching the four-gate `execution ==
# -- "SUCCESS"` predicate used by the iteration controller). ----------------- #
SUCCESS = "SUCCESS"   # every code cell executed without error
ERROR = "ERROR"       # a code cell raised at runtime
TIMEOUT = "TIMEOUT"   # per-cell timeout fired, or the total budget was exceeded
KILLED = "KILLED"     # the kernel died / was unreachable

# Environment injected into the kernel when networking is disallowed (advisory).
_NETWORK_DENY_ENV = {
    "IPY_ALLOW_NETWORK": "0",
    "NB_AUDIT_ALLOW_NETWORK": "0",
}


# --------------------------------------------------------------------------- #
# Namespace serialization (pure, unit-testable)
# --------------------------------------------------------------------------- #
def is_capturable(value: Any) -> bool:
    """Return whether ``value`` can safely round-trip through pickle.

    Excludes modules, callables, classes, objects whose type is defined in the
    notebook itself (``__main__`` — unpicklable by reference in the parent), and
    anything ``pickle`` cannot serialize. This keeps the captured namespace
    faithful (real numpy/torch objects survive) while never crashing the capture
    step on notebook-local classes or open file handles.
    """
    if isinstance(value, types.ModuleType):
        return False
    if isinstance(value, type) or callable(value):
        return False
    if getattr(type(value), "__module__", None) == "__main__":
        return False
    try:
        pickle.dumps(value, protocol=4)
    except Exception:
        return False
    return True


def serialize_namespace(namespace: Mapping[str, Any]) -> dict[str, Any]:
    """Filter ``namespace`` to the subset that can be re-materialized later."""
    return {
        str(key): value
        for key, value in namespace.items()
        if not str(key).startswith("_") and is_capturable(value)
    }


def _capture_cell_source(path: str) -> str:
    """Source for the injected final cell that dumps the namespace to ``path``.

    The cell runs in the SAME kernel that executed the notebook, so its
    ``globals()`` is the executed namespace. Only non-underscore, capturable
    values are written; notebook-local classes and unpicklable handles are
    skipped via :func:`serialize_namespace`'s filter (reproduced inline because
    this source is evaluated inside the kernel process).
    """
    return (
        "import pickle, types\n"
        "_nb_audit_out = {}\n"
        "for _nb_name, _nb_value in list(globals().items()):\n"
        "    if _nb_name.startswith('_'):\n"
        "        continue\n"
        "    if isinstance(_nb_value, types.ModuleType):\n"
        "        continue\n"
        "    if isinstance(_nb_value, type) or callable(_nb_value):\n"
        "        continue\n"
        "    try:\n"
        "        if getattr(type(_nb_value), '__module__', None) == '__main__':\n"
        "            continue\n"
        "        pickle.dumps(_nb_value, protocol=4)\n"
        "    except Exception:\n"
        "        continue\n"
        "    _nb_audit_out[_nb_name] = _nb_value\n"
        f"with open({path!r}, 'wb') as _nb_fh:\n"
        "    pickle.dump(_nb_audit_out, _nb_fh, protocol=4)\n"
    )


def _load_namespace(path: Path) -> dict[str, Any]:
    """Unpickle the captured namespace; return ``{}`` on any failure."""
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            data = pickle.load(fh)
    except Exception:
        return {}
    if isinstance(data, Mapping):
        return {str(key): value for key, value in data.items()}
    return {}


def _as_notebook_node(nb: Any) -> Any:
    """Normalize a path / dict / NotebookNode into a fresh NotebookNode."""
    if isinstance(nb, (str, os.PathLike)):
        return nbformat.read(os.fspath(nb), as_version=4)
    if isinstance(nb, Mapping):
        return nbformat.from_dict(copy.deepcopy(dict(nb)))
    raise TypeError(f"unsupported notebook type: {type(nb).__name__!r}")


def _find_error_cells(nb: Any) -> list[tuple[int, str, str]]:
    """Return ``(cell_index, ename, evalue)`` for every cell with an error output."""
    cells = nb.get("cells", []) if isinstance(nb, Mapping) else getattr(nb, "cells", [])
    errors: list[tuple[int, str, str]] = []
    for index, cell in enumerate(cells):
        outputs = (
            cell.get("outputs", [])
            if isinstance(cell, Mapping)
            else getattr(cell, "outputs", [])
        )
        for output in outputs or []:
            if isinstance(output, Mapping) and output.get("output_type") == "error":
                errors.append(
                    (index, output.get("ename", ""), output.get("evalue", ""))
                )
                break
    return errors


def _cell_id(nb: Any, cell_index: int | None) -> str:
    if nb is None or cell_index is None or cell_index < 0:
        return ""
    cells = nb.get("cells", []) if isinstance(nb, Mapping) else getattr(nb, "cells", [])
    try:
        cell = cells[cell_index]
    except (IndexError, TypeError):
        return ""
    if isinstance(cell, Mapping):
        return str(cell.get("id", "") or "")
    return str(getattr(cell, "id", "") or "")


def build_execution_finding(
    nb: Any,
    cell_index: int | None,
    ename: str = "",
    evalue: str = "",
    status: str = ERROR,
) -> Finding:
    """Build the severity-10 ``execution`` finding for a failed run (§18)."""
    reason = {
        TIMEOUT: "timed out",
        KILLED: "was aborted because the kernel died",
        ERROR: "failed",
    }.get(status, "failed")
    detail = f": {evalue}" if evalue else ""
    if ename and ename not in ("", "builtins.TimeoutError"):
        detail = f" ({ename}){detail}"
    return Finding(
        id="",
        severity=10,
        classification=Classification.NEW,
        category="execution",
        location=Location(cell=_cell_id(nb, cell_index)),
        issue=f"Notebook execution {reason}{detail}",
        root_cause=(
            "A code cell raised at runtime, timed out, or killed the kernel, so "
            "the notebook could not execute to completion"
        ),
        impact=(
            "The patched notebook is not runnable; its results and any downstream "
            "QA are invalid and must never be reported as PASS"
        ),
        correction=(
            "Fix the failing cell so the notebook executes cleanly end-to-end "
            "(no unhandled exceptions, no unbounded loops, no kernel crash)"
        ),
        status=Status.UNRESOLVED,
    )


# --------------------------------------------------------------------------- #
# Execution result
# --------------------------------------------------------------------------- #
@dataclass
class ExecutionResult:
    """Outcome of one notebook execution attempt."""

    status: str
    namespace: Mapping[str, Any] = field(default_factory=dict)
    executed_nb: Any = None
    cell_index: int | None = None
    error_message: str = ""
    error_type: str = ""
    finding: Finding | None = None

    @property
    def ok(self) -> bool:
        return self.status == SUCCESS


# --------------------------------------------------------------------------- #
# Executor
# --------------------------------------------------------------------------- #
class _TrackingNotebookClient(NotebookClient):
    """nbclient subclass that records the index of the most recently tried cell.

    Also tracks whether a per-cell timeout fired: nbclient's default behaviour is
    to *interrupt* the kernel on timeout (``interrupt_on_timeout=True``) and let
    the interrupted cell surface as a ``KeyboardInterrupt`` error output, which
    with ``allow_errors=True`` does NOT raise. We must therefore observe the
    timeout ourselves so the executor can report a distinct ``TIMEOUT`` status
    (and its severity-10 finding) instead of a generic ``ERROR``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.last_cell_index = -1
        self.timed_out = False
        self.timeout_cell_index: int | None = None

    async def async_execute_cell(self, cell: Any, cell_index: int, **kwargs: Any) -> Any:
        self.last_cell_index = cell_index
        return await super().async_execute_cell(cell, cell_index, **kwargs)

    async def _async_handle_timeout(self, timeout: int, cell: Any = None) -> Any:
        self.timed_out = True
        self.timeout_cell_index = self.last_cell_index
        return await super()._async_handle_timeout(timeout, cell)


class NotebookExecutor:
    """Executes a notebook in a fresh kernel and captures its namespace."""

    def __init__(
        self,
        config: AuditConfig | None = None,
        run_dir: str | os.PathLike[str] | None = None,
        namespace_file: str = ".nb_audit_namespace.pkl",
    ) -> None:
        self.config = config or AuditConfig()
        self.execution = self.config.execution
        self.run_dir = Path(run_dir).resolve() if run_dir else Path.cwd()
        self.namespace_file = namespace_file

    # -- helpers ------------------------------------------------------------ #
    def _capture_path(self) -> Path:
        return self.run_dir / self.namespace_file

    def kernel_env(self, allow_network: bool | None = None) -> dict[str, str]:
        """Environment injected into the kernel (advisory network isolation)."""
        allow = self.execution.allow_network if allow_network is None else allow_network
        if allow:
            return {}
        return dict(_NETWORK_DENY_ENV)

    def _build_client(
        self, nb: Any, timeout: int, allow_network: bool | None
    ) -> tuple[_TrackingNotebookClient, dict[str, str]]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        env = self.kernel_env(allow_network)
        client = _TrackingNotebookClient(
            nb,
            kernel_name=self.execution.kernel_name,
            timeout=timeout,
            interrupt_on_timeout=True,
            error_on_timeout={
                "ename": "TimeoutError",
                "evalue": "Cell execution timed out",
                "traceback": [],
            },
            allow_errors=True,  # record errors as cell outputs; we scan them after
            resources={"metadata": {"path": str(self.run_dir)}},
            shell_timeout_interval=1,
        )
        return client, env

    def _failure(
        self,
        client: _TrackingNotebookClient,
        status: str,
        message: str,
        error_type: str = "",
        cell_index: int | None = None,
    ) -> ExecutionResult:
        index = cell_index if cell_index is not None else (
            client.last_cell_index if client.last_cell_index >= 0 else None
        )
        return ExecutionResult(
            status=status,
            cell_index=index,
            error_message=message,
            error_type=error_type,
            executed_nb=client.nb,
            finding=build_execution_finding(client.nb, index, error_type, message, status),
        )

    # -- main entry --------------------------------------------------------- #
    async def execute(
        self,
        nb: Any,
        *,
        timeout: int | None = None,
        allow_network: bool | None = None,
    ) -> ExecutionResult:
        """Execute ``nb`` and return the result.

        ``timeout`` overrides ``execution.timeout_seconds`` as the per-cell
        timeout (seconds). ``allow_network`` overrides
        ``execution.allow_network``. The kernel namespace is captured into the
        run dir and re-materialized into ``result.namespace``.
        """
        node = _as_notebook_node(nb)
        per_cell = int(timeout) if timeout is not None else int(
            self.execution.timeout_seconds
        )

        capture_path = self._capture_path()
        if capture_path.exists():
            capture_path.unlink()

        node.cells.append(
            nbformat.v4.new_code_cell(_capture_cell_source(str(capture_path)))
        )

        client, env = self._build_client(node, per_cell, allow_network)
        code_cells = sum(1 for c in node.cells if c.get("cell_type") == "code")
        total_budget = max(per_cell, 1) * (code_cells + 1)

        task = asyncio.create_task(client.async_execute(env=env))
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=total_budget)
        except CellTimeoutError as exc:
            # Defensive — nbclient only raises this with interrupt_on_timeout off;
            # we keep interrupt_on_timeout on, but still map it correctly.
            return self._failure(client, TIMEOUT, str(exc), "CellTimeoutError")
        except DeadKernelError as exc:
            return self._failure(client, KILLED, str(exc), "DeadKernelError")
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - cleanup best effort
                pass
            return self._failure(
                client,
                TIMEOUT,
                f"Total execution budget exceeded ({total_budget}s)",
                "asyncio.TimeoutError",
            )
        except CellExecutionError as exc:  # defensive — allow_errors normally absorbs this
            return self._failure(client, ERROR, f"{exc.ename}: {exc.evalue}", "CellExecutionError")
        except Exception as exc:  # noqa: BLE001 - convert any failure to a sev-10 finding
            return self._failure(
                client, ERROR, str(exc), type(exc).__name__, client.last_cell_index
            )

        errors = _find_error_cells(client.nb)
        if client.timed_out:
            index = client.timeout_cell_index
            return ExecutionResult(
                status=TIMEOUT,
                namespace=_load_namespace(capture_path),
                executed_nb=client.nb,
                cell_index=index,
                error_message="Cell execution timed out",
                error_type="TimeoutError",
                finding=build_execution_finding(
                    client.nb, index, "TimeoutError", "Cell execution timed out", TIMEOUT
                ),
            )
        if errors:
            index, ename, evalue = errors[0]
            return ExecutionResult(
                status=ERROR,
                namespace=_load_namespace(capture_path),
                executed_nb=client.nb,
                cell_index=index,
                error_message=evalue,
                error_type=ename,
                finding=build_execution_finding(client.nb, index, ename, evalue, ERROR),
            )

        return ExecutionResult(
            status=SUCCESS,
            namespace=_load_namespace(capture_path),
            executed_nb=client.nb,
        )

    def execute_sync(self, nb: Any, **kwargs: Any) -> ExecutionResult:
        """Synchronous convenience wrapper (used by tests and the controller)."""
        return asyncio.run(self.execute(nb, **kwargs))
