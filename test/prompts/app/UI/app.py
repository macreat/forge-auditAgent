"""Flet GUI for test-prompts-app.

Provides tabs for hardware info, model download, server control, settings,
benchmark, audit, and notebook construction. The tab set is driven by the
single module-level :data:`TAB_SPEC` list, which supplies both the tab labels
and the panel registry keys used to assemble ``panels[]`` and ``ft.Tabs``.
"""

import datetime
import os
from pathlib import Path

import flet as ft

from app.api.local import (
    checkHardware,
    haveGpuAccel,
    listAvailableModels,
    listAvailableQuantizations,
    downloadSelectedModel,
    AsyncLlamaServer,
)
from app.api.utils import ProviderError, create_provider, mask_secret
from app.audit.export import to_json, to_pdf
from app.audit.pipeline import AuditPipeline
from app.config import settings
from app.config.paths import defaultReportsDir
from app.construct import loaders
from app.construct.export import save_notebook
from app.construct.models import ConstructSession
from app.construct.scaffold import CANONICAL_HEADERS, build_scaffold
from app.construct.writer import draft_sections


class AppState:
    def __init__(self):
        self.server = None
        self.serverRunning = False
        self.hardware = None
        # Construct pipeline state (load -> scaffold -> draft -> export).
        self.construct = None
        # Busy guard: true while a construct draft is running; prevents
        # concurrent runs and disables the construct buttons (RSL-2).
        self.constructBusy = False


state = AppState()

#: Single source of truth for the tab set. Drives both the ``ft.TabBar``
#: labels and the ``panels[]`` order assembled at the end of :func:`build`.
#: The 6 pre-existing tabs keep their original labels and order; the 7th
#: (Construct) tab is registered here too.
TAB_SPEC = [
    {"label": "Hardware", "panel": "hardwarePanel"},
    {"label": "Models", "panel": "modelsPanel"},
    {"label": "Server", "panel": "serverPanel"},
    {"label": "Settings", "panel": "settingsPanel"},
    {"label": "Benchmark", "panel": "benchmarkPanel"},
    {"label": "Audit", "panel": "auditPanel"},
    {"label": "Construct", "panel": "constructPanel"},
]

#: Source type -> construct loader function name (1:1 mapping used to keep
#: the Construct panel's source-type and loader selectors in sync).
_SOURCE_LOADER_MAP = {
    "local": "load_local",
    "github": "load_github",
    "http": "load_http",
    "drive": "load_drive",
    "kaggle": "load_kaggle",
}

_SOURCE_HINTS = {
    "local": "/path/to/source.md",
    "github": "https://github.com/{owner}/{repo}/blob/{ref}/{path}",
    "http": "https://example.com/source.txt",
    "drive": "https://drive.google.com/uc?export=download&id=... or file ID",
    "kaggle": "owner/slug (or kaggle.com/datasets/owner/slug URL)",
}


def _resolveSecretField(field_value, stored_key):
    """Keep the stored key when the field still shows its masked form;
    store the typed value (or an empty string to clear) otherwise.

    Keys are never logged: the value returned here goes into the config
    dict only (R19, RSK-3).
    """
    if field_value == mask_secret(stored_key):
        return stored_key
    return (field_value or "").strip()


def _parse_kaggle(raw):
    """Split a Kaggle dataset reference into ``(owner, slug)``.

    Accepts ``owner/slug``, a ``kaggle.com/datasets/{owner}/{slug}`` URL, an
    API download path (``kaggle.com/api/v1/datasets/download/{owner}/{slug}``),
    or a bare API path. Returns ``("", "")`` when unparseable.
    """
    value = (raw or "").strip()
    if "kaggle.com" in value:
        value = value.split("kaggle.com")[-1].lstrip("/")
    parts = [part for part in value.split("/") if part]
    if "datasets" in parts:
        index = parts.index("datasets")
        if index + 1 < len(parts) and parts[index + 1] == "download":
            index += 1  # api path form: datasets/download/{owner}/{slug}
        if index + 2 < len(parts):
            return parts[index + 1], parts[index + 2]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


def build(page: ft.Page):
    page.title = "test-prompts-app"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 900
    page.window.height = 650
    page.scroll = ft.ScrollMode.AUTO

    cfg = settings.load()

    hardwareText = ft.Text("Loading hardware info ...", selectable=True)
    gpuAccelText = ft.Text("")
    modelList = ft.ListView(expand=True, spacing=4, height=200)
    quantList = ft.ListView(expand=True, spacing=4, height=200)
    downloadStatus = ft.Text("")
    progressBar = ft.ProgressBar(visible=False)

    serverStatus = ft.Text("Server: stopped", color=ft.Colors.RED_400)
    serverHost = ft.TextField(label="Host", value=cfg["host"], width=120, height=48)
    serverPort = ft.TextField(label="Port", value=str(cfg["port"]), width=90, height=48)
    serverModel = ft.TextField(label="Model path", value=cfg.get("lastModelPath", ""), height=48, expand=True)
    nGpuLayers = ft.TextField(label="GPU layers", value=str(cfg["nGpuLayers"]), width=100, height=48)
    nCtx = ft.TextField(label="Context", value=str(cfg["nCtx"]), width=100, height=48)

    modelDropdown = ft.Dropdown(
        label="Choose downloaded model",
        options=[],
        on_select=lambda e: _selectModel(e),
        expand=True,
        height=48,
    )

    def _selectModel(e):
        if modelDropdown.value:
            serverModel.value = modelDropdown.value
            page.update()

    def refreshModelList():
        modelsDir = cfg["modelsDir"]
        modelDropdown.options.clear()
        try:
            for entry in sorted(os.scandir(modelsDir), key=lambda e: e.name):
                if entry.is_file() and entry.name.endswith(".gguf"):
                    modelDropdown.options.append(ft.DropdownOption(key=entry.path, text=entry.name))
        except FileNotFoundError:
            pass
        if modelDropdown.options:
            modelDropdown.value = modelDropdown.options[0].key
            serverModel.value = modelDropdown.value
        else:
            modelDropdown.value = None
        page.update()

    settingsModelsDir = ft.TextField(label="Models directory", value=cfg["modelsDir"], height=48, expand=True)

    # --- LLM provider settings (R19, RSK-3): provider selector + masked
    # API key fields. Keys are rendered masked (mask_secret) and are never
    # written to status/log text.
    providerDropdown = ft.Dropdown(
        label="LLM provider",
        options=[
            ft.DropdownOption(key="local", text="Local (llama.cpp)"),
            ft.DropdownOption(key="openai", text="OpenAI"),
            ft.DropdownOption(key="anthropic", text="Anthropic"),
            ft.DropdownOption(key="ollama", text="Ollama"),
        ],
        value=cfg.get("llmProvider", "local"),
        width=240,
        height=48,
    )
    openaiKeyField = ft.TextField(
        label="OpenAI API key",
        value=mask_secret(cfg.get("openaiApiKey", "")),
        password=True,
        can_reveal_password=True,
        expand=True,
        height=48,
    )
    anthropicKeyField = ft.TextField(
        label="Anthropic API key",
        value=mask_secret(cfg.get("anthropicApiKey", "")),
        password=True,
        can_reveal_password=True,
        expand=True,
        height=48,
    )
    ollamaModelField = ft.TextField(
        label="Ollama model",
        value=cfg.get("ollamaModel", "llama3.2"),
        expand=True,
        height=48,
    )

    def log(msg):
        downloadStatus.value = msg
        page.update()

    def loadHardware():
        state.hardware = checkHardware()
        hw = state.hardware
        gpuInfo = hw["gpu"]
        gpuName = gpuInfo["primary"]["name"] if gpuInfo.get("primary") else "none"
        gpuVram = f'{gpuInfo["primary"]["vramGb"]}GB' if gpuInfo.get("primary") and gpuInfo["primary"].get("vramGb") else "—"
        hardwareText.value = (
            f'OS: {hw["os"]["platform"]} ({hw["os"]["architecture"]})  '
            f'RAM: {hw["systemRam"]["totalGb"]}GB ({hw["systemRam"]["availableGb"]}GB free)\n'
            f'GPU: {gpuName}  VRAM: {gpuVram}  '
            f'Recommendation: {hw["recommendation"]["mode"].upper()} up to {hw["recommendation"]["size"]/1e9:.0f}B params'
        )
        gpuAccelText.value = "GPU acceleration available" if haveGpuAccel() else "CPU-only mode"
        gpuAccelText.color = ft.Colors.GREEN_400 if haveGpuAccel() else ft.Colors.ORANGE_400
        page.update()

    def searchModels(e=None):
        modelList.controls.clear()
        modelList.controls.append(ft.Text("Searching HuggingFace ..."))
        page.update()
        available = listAvailableModels(state.hardware)
        modelList.controls.clear()
        if not available:
            modelList.controls.append(ft.Text("No models found."))
        for m in available:
            modelList.controls.append(
                ft.TextButton(
                    m,
                    on_click=lambda e, mid=m: listQuantizations(mid),
                )
            )
        page.update()

    def listQuantizations(modelId):
        quantList.controls.clear()
        quantList.controls.append(ft.Text(f"Loading quants for {modelId.split('/')[-1]} ..."))
        page.update()
        quants = listAvailableQuantizations(modelId)
        quantList.controls.clear()
        if not quants:
            quantList.controls.append(ft.Text("No GGUF files found."))
        for name, sizeMb in sorted(quants.items()):
            quantList.controls.append(
                ft.TextButton(
                    f"{name}  ({sizeMb} MB)",
                    on_click=lambda e, mid=modelId, q=name: downloadModel(mid, q),
                )
            )
        page.update()

    def downloadModel(modelId, quantization):
        progressBar.visible = True
        progressBar.value = None
        log(f"Downloading {modelId} ({quantization}) ...")
        page.update()
        try:
            path = downloadSelectedModel(modelId, quantization)
            serverModel.value = path
            log(f"Downloaded: {path}")
        except Exception as ex:
            log(f"Error: {ex}")
        finally:
            progressBar.visible = False
            page.update()

    async def startServer(e):
        path = serverModel.value.strip()
        if not path or not os.path.isfile(path):
            serverStatus.value = "Error: model file not found"
            serverStatus.color = ft.Colors.RED_400
            page.update()
            return
        try:
            port = int(serverPort.value)
            host = serverHost.value.strip()
            layers = int(nGpuLayers.value)
            ctx = int(nCtx.value)
        except ValueError:
            serverStatus.value = "Error: invalid port/layers/context"
            serverStatus.color = ft.Colors.RED_400
            page.update()
            return
        state.server = AsyncLlamaServer(path, host=host, port=port, nGpuLayers=layers, nCtx=ctx)
        serverStatus.value = "Server: starting ..."
        serverStatus.color = ft.Colors.YELLOW_400
        page.update()
        try:
            await state.server.start()
            state.serverRunning = True
            serverStatus.value = f"Server: running at http://{host}:{port}"
            serverStatus.color = ft.Colors.GREEN_400
        except Exception as ex:
            serverStatus.value = f"Server error: {ex}"
            serverStatus.color = ft.Colors.RED_400
        page.update()

    async def stopServer(e):
        if state.server and state.serverRunning:
            serverStatus.value = "Server: stopping ..."
            page.update()
            await state.server.stop()
            state.serverRunning = False
            serverStatus.value = "Server: stopped"
            serverStatus.color = ft.Colors.RED_400
            page.update()

    def saveSettings(e):
        try:
            # Snapshot the stored keys before building the new config dict
            # (the dict literal rebinds `cfg`, so read first).
            saved_openai_key = cfg.get("openaiApiKey", "")
            saved_anthropic_key = cfg.get("anthropicApiKey", "")
            new_cfg = {
                "host": serverHost.value.strip(),
                "port": int(serverPort.value),
                "nGpuLayers": int(nGpuLayers.value),
                "nCtx": int(nCtx.value),
                "modelsDir": settingsModelsDir.value.strip(),
                "lastModelPath": serverModel.value.strip(),
                "llmProvider": (providerDropdown.value or "local").strip().lower(),
                "openaiApiKey": _resolveSecretField(
                    openaiKeyField.value, saved_openai_key
                ),
                "anthropicApiKey": _resolveSecretField(
                    anthropicKeyField.value, saved_anthropic_key
                ),
                "ollamaModel": ollamaModelField.value.strip() or "llama3.2",
            }
            settings.save(new_cfg)
            log("Settings saved.")
        except ValueError:
            log("Error: invalid port/layers/context values.")

    # --- Panels ---
    hardwarePanel = ft.Column(
        [hardwareText, gpuAccelText],
        spacing=10,
        expand=True,
    )

    modelsPanel = ft.Column(
        [
            ft.Text("Available models:", weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("Refresh", on_click=searchModels),
            modelList,
            ft.Divider(),
            ft.Text("Pick quantization:", weight=ft.FontWeight.BOLD),
            quantList,
            downloadStatus,
            progressBar,
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    serverPanel = ft.Column(
        [
            serverStatus,
            ft.Row([serverHost, serverPort, nGpuLayers, nCtx]),
            ft.Row([modelDropdown, ft.ElevatedButton("Refresh", on_click=lambda _: refreshModelList())]),
            ft.Row([serverModel]),
            ft.Divider(),
            ft.Row(
                [
                    ft.ElevatedButton("Start", on_click=lambda e: page.run_task(startServer, e), bgcolor=ft.Colors.GREEN_700),
                    ft.ElevatedButton("Stop", on_click=lambda e: page.run_task(stopServer, e), bgcolor=ft.Colors.RED_700),
                ]
            ),
        ],
        spacing=10,
        expand=True,
    )

    settingsPanel = ft.Column(
        [
            ft.Text("Models directory:", weight=ft.FontWeight.BOLD),
            settingsModelsDir,
            ft.Divider(),
            ft.Text("LLM provider:", weight=ft.FontWeight.BOLD),
            ft.Row([providerDropdown]),
            ft.Text(
                "API keys are stored in the local config file and never logged.",
                size=12,
                color=ft.Colors.GREY_400,
            ),
            openaiKeyField,
            anthropicKeyField,
            ollamaModelField,
            ft.Divider(),
            ft.ElevatedButton("Save", on_click=saveSettings),
        ],
        spacing=10,
        expand=True,
    )

    # --- Benchmark Panel ---
    benchmarkModelChecks = ft.Column(spacing=4)
    benchmarkApiList = ft.Column(spacing=4)
    apiUrlField = ft.TextField(
        label="API endpoint URL", hint_text="http://host:port/v1", expand=True, height=48
    )
    promptField = ft.TextField(
        label="Prompt",
        hint_text="Paste your prompt here...",
        multiline=True,
        min_lines=5,
        max_lines=10,
        expand=True,
    )
    benchmarkStatus = ft.Text("")
    resultsColumn = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def refreshBenchmarkModels():
        modelsDir = cfg["modelsDir"]
        benchmarkModelChecks.controls.clear()
        try:
            for entry in sorted(os.scandir(modelsDir), key=lambda e: e.name):
                if entry.is_file() and entry.name.endswith(".gguf"):
                    benchmarkModelChecks.controls.append(
                        ft.Checkbox(label=entry.name, value=True)
                    )
        except FileNotFoundError:
            pass
        page.update()

    def addApiEndpoint(e):
        url = apiUrlField.value.strip()
        if url:
            benchmarkApiList.controls.append(
                ft.Row(
                    [
                        ft.Checkbox(label=f"API: {url}", value=True, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            on_click=lambda e, u=url: removeApiEndpoint(u),
                        ),
                    ]
                )
            )
            apiUrlField.value = ""
            page.update()

    def removeApiEndpoint(url):
        benchmarkApiList.controls = [
            c
            for c in benchmarkApiList.controls
            if not (
                isinstance(c, ft.Row)
                and isinstance(c.controls[0], ft.Checkbox)
                and url in c.controls[0].label
            )
        ]
        page.update()

    def readyBenchmark(e):
        selected = []
        for check in benchmarkModelChecks.controls:
            if isinstance(check, ft.Checkbox) and check.value:
                selected.append({"name": check.label, "type": "gguf"})
        for row in benchmarkApiList.controls:
            if isinstance(row, ft.Row):
                check = row.controls[0]
                if isinstance(check, ft.Checkbox) and check.value:
                    label = check.label
                    url = label.replace("API: ", "")
                    selected.append({"name": label, "type": "api", "endpoint": url})
        if not selected:
            benchmarkStatus.value = "No models or APIs selected."
            page.update()
            return
        benchmarkStatus.value = f"Ready: {len(selected)} model(s)/API(s) selected."
        resultsColumn.controls.clear()
        for item in selected:
            resultsColumn.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                item["name"],
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_400,
                            ),
                            ft.TextField(
                                value=f"[Response from {item['name']} will appear here]",
                                multiline=True,
                                min_lines=3,
                                read_only=True,
                                expand=True,
                            ),
                        ]
                    ),
                    padding=10,
                    border=ft.Border(
                        top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                        left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                        right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                        bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    ),
                    border_radius=8,
                    margin=ft.Margin(left=0, top=0, right=0, bottom=8),
                )
            )
        page.update()

    def sendToAll(e):
        prompt = promptField.value.strip()
        if not prompt:
            benchmarkStatus.value = "Please enter a prompt."
            page.update()
            return
        if not resultsColumn.controls:
            benchmarkStatus.value = "Click 'Ready' first to select models."
            page.update()
            return
        for container in resultsColumn.controls:
            if isinstance(container, ft.Container):
                col = container.content
                if isinstance(col, ft.Column) and len(col.controls) >= 2:
                    name_text = col.controls[0]
                    response_field = col.controls[1]
                    if isinstance(response_field, ft.TextField):
                        response_field.value = (
                            f"Response from {name_text.value}:\n"
                            f"Echo: {prompt}\n\n"
                            f"[This is a placeholder response]"
                        )
        benchmarkStatus.value = "Sent! (placeholder responses)"
        page.update()

    benchmarkPanel = ft.Column(
        [
            ft.Text("Benchmark Models & APIs", weight=ft.FontWeight.BOLD, size=16),
            ft.Divider(),
            ft.Row(
                [
                    ft.Text("Available models:", weight=ft.FontWeight.BOLD),
                    ft.ElevatedButton(
                        "Refresh", on_click=lambda _: refreshBenchmarkModels()
                    ),
                    ft.ElevatedButton(
                        "Ready", on_click=readyBenchmark, bgcolor=ft.Colors.BLUE_700
                    ),
                ]
            ),
            benchmarkModelChecks,
            ft.Divider(),
            ft.Text("API Endpoints:", weight=ft.FontWeight.BOLD),
            benchmarkApiList,
            ft.Row([apiUrlField, ft.ElevatedButton("+ Add", on_click=addApiEndpoint)]),
            ft.Divider(),
            ft.Text("Prompt:", weight=ft.FontWeight.BOLD),
            promptField,
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Send to All",
                        on_click=sendToAll,
                        bgcolor=ft.Colors.GREEN_700,
                    ),
                    benchmarkStatus,
                ]
            ),
            ft.Divider(),
            ft.Text("Results:", weight=ft.FontWeight.BOLD, size=14),
            resultsColumn,
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # --- Audit Panel ---
    _pass_labels = [
        "Structural Overview",
        "Reproducibility",
        "Data Integrity",
        "ML Correctness",
        "Code Quality",
        "Deployment Readiness",
    ]

    auditData = {"notebook": None, "report": None}

    # --- Source: local path ---
    localPathField = ft.TextField(
        label="Local path",
        hint_text="/path/to/notebook.ipynb",
        expand=True,
        height=48,
    )
    loadLocalBtn = ft.ElevatedButton(
        "Load Local",
        on_click=lambda _: _load_local(),
    )

    # --- Source: notebooks database ---
    # Path: test/prompts/notebooks/  (__file__ is app/UI/app.py → up 3 levels to test/prompts/)
    _NB_DB_DIR = Path(__file__).resolve().parents[2] / "notebooks"

    notebookDropdown = ft.Dropdown(
        label="Notebook DB",
        hint_text="Pick a notebook...",
        options=[],
        expand=True,
        height=48,
    )
    notebookDropdown.on_change = lambda e: _load_from_db(e)

    def _scan_notebooks_db():
        notebookDropdown.options.clear()
        nb_dir = _NB_DB_DIR
        if not nb_dir.is_dir():
            auditStatus.value = f"Notebook DB not found: {nb_dir}"
            page.update()
            return
        # Collect .ipynb, .py, and other text-based files
        files = sorted(nb_dir.iterdir(), key=lambda p: p.name)
        for f in files:
            if f.is_file() and f.suffix in (".ipynb", ".py", ".md", ".txt"):
                notebookDropdown.options.append(
                    ft.DropdownOption(key=str(f), text=f.name)
                )
        if notebookDropdown.options:
            notebookDropdown.value = notebookDropdown.options[0].key
            auditStatus.value = f"Found {len(notebookDropdown.options)} file(s) in notebooks DB"
            # Auto-load the first one
            _load_notebook_from_path(notebookDropdown.options[0].key)
        else:
            auditStatus.value = "No notebook files found in DB directory."
        page.update()

    def _load_from_db(e):
        if notebookDropdown.value:
            _load_notebook_from_path(notebookDropdown.value)

    def _load_notebook_from_path(path: str):
        auditStatus.value = f"Loading {Path(path).name} ..."
        page.update()
        try:
            from app.audit.loader import load_notebook

            nb = load_notebook(path)
            auditData["notebook"] = nb
            if nb.valid:
                auditStatus.value = (
                    f"Loaded: {nb.filename} ({len(nb.cells)} cells)"
                )
            else:
                auditStatus.value = (
                    f"Error: {'; '.join(nb.validation_errors)}"
                )
        except Exception as ex:
            auditStatus.value = f"Error: {ex}"
        page.update()

    # --- Source: GitHub URL ---
    githubUrlField = ft.TextField(
        label="GitHub URL",
        hint_text="https://raw.githubusercontent.com/...",
        expand=True,
        height=48,
    )
    loadBtn = ft.ElevatedButton("Load", on_click=lambda _: _load_source())

    def _normalize_github_url(url: str) -> str:
        """Convert a regular GitHub blob URL to a raw.githubusercontent.com URL."""
        # Already a raw URL
        if "raw.githubusercontent.com" in url:
            return url
        # Convert github.com/user/repo/blob/branch/path -> raw
        import re

        m = re.match(
            r"https?://github\.com/([^/]+/[^/]+)/blob/([^/]+)/(.+)", url
        )
        if m:
            return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
        return url

    def _load_source():
        url = githubUrlField.value.strip()
        if not url:
            auditStatus.value = "Enter a GitHub URL."
            page.update()
            return
        raw_url = _normalize_github_url(url)
        auditStatus.value = "Fetching notebook ..."
        page.update()
        try:
            from app.audit.loader import load_from_github

            nb = load_from_github(raw_url)
            auditData["notebook"] = nb
            if nb.valid:
                auditStatus.value = (
                    f"Loaded: {nb.filename} ({len(nb.cells)} cells)"
                )
            else:
                auditStatus.value = (
                    f"Error loading: {'; '.join(nb.validation_errors)}"
                )
        except Exception as ex:
            auditStatus.value = f"Error: {ex}"
        page.update()

    # --- Local path loading ---
    def _load_local():
        path = localPathField.value.strip()
        if not path:
            auditStatus.value = "Enter a file path."
            page.update()
            return
        _load_notebook_from_path(path)

    # --- Audit execution ---
    focusCheckboxes = ft.Column(spacing=4)
    _focus_checks: list[ft.Checkbox] = []
    for label in _pass_labels:
        cb = ft.Checkbox(label=label, value=True)
        _focus_checks.append(cb)
        focusCheckboxes.controls.append(cb)

    runAuditBtn = ft.ElevatedButton(
        "Run Audit",
        icon=ft.Icons.PLAY_ARROW,
        on_click=lambda e: page.run_task(_run_audit, e),
    )

    resultsColumn = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    exportPdfBtn = ft.ElevatedButton(
        "Export PDF", on_click=lambda _: _export("pdf")
    )
    exportJsonBtn = ft.ElevatedButton(
        "Export JSON", on_click=lambda _: _export("json")
    )

    auditStatus = ft.Text("")

    async def _run_audit(e):
        nb = auditData["notebook"]
        if nb is None:
            auditStatus.value = "Load a notebook first."
            page.update()
            return

        selected = [cb.label for cb in _focus_checks if cb.value]
        focus = selected if len(selected) < len(_pass_labels) else None

        resultsColumn.controls.clear()
        auditStatus.value = "Starting audit ..."
        page.update()

        pipeline = AuditPipeline()

        def progress_cb(result):
            card = _build_result_card(result)
            resultsColumn.controls.append(card)
            auditStatus.value = (
                f"Pass {result.pass_number}/6: "
                f"{result.pass_name} - {result.status}"
            )
            page.update()

        try:
            report = pipeline.run(nb, focus_areas=focus, progress_cb=progress_cb)
            auditData["report"] = report
            auditStatus.value = (
                f"Audit complete: {report.status} "
                f"({len(report.passes)} passes)"
            )
        except Exception as ex:
            auditStatus.value = f"Audit error: {ex}"
        page.update()

    def _build_result_card(result):
        score_colors = {
            "low": ft.Colors.GREEN_400,
            "moderate": ft.Colors.ORANGE_400,
            "high": ft.Colors.RED_400,
        }
        sc = result.score.lower() if result.score else ""
        score_color = score_colors.get(sc, ft.Colors.GREY_400)

        badge = ft.Container(
            content=ft.Text(
                result.score.upper() if result.score else result.status.upper(),
                color=ft.Colors.WHITE,
                weight=ft.FontWeight.BOLD,
                size=11,
            ),
            bgcolor=score_color,
            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
            border_radius=4,
        )

        findings_count = len(result.findings)
        detail_content = ft.Column(spacing=4)

        if result.status == "error":
            detail_content.controls.append(
                ft.Text(result.deliverable_text, color=ft.Colors.RED_400)
            )
        elif result.findings:
            icon_map = {
                "error": ft.Icons.ERROR,
                "warning": ft.Icons.WARNING,
                "info": ft.Icons.INFO,
            }
            color_map = {
                "error": ft.Colors.RED_400,
                "warning": ft.Colors.ORANGE_400,
                "info": ft.Colors.BLUE_400,
            }
            for finding in result.findings:
                cell_ref = (
                    f"Cell {finding.cell_index}"
                    if finding.cell_index is not None
                    else "Notebook"
                )
                detail_content.controls.append(
                    ft.Row(
                        [
                            ft.Icon(
                                icon_map.get(
                                    finding.severity, ft.Icons.CIRCLE
                                ),
                                size=16,
                                color=color_map.get(
                                    finding.severity, ft.Colors.GREY_400
                                ),
                            ),
                            ft.Text(
                                f"[{cell_ref}] [{finding.category}] "
                                f"{finding.message}",
                                size=12,
                                expand=True,
                            ),
                        ],
                        spacing=4,
                    )
                )
        else:
            detail_content.controls.append(
                ft.Text("No findings.", size=12)
            )

        expander = ft.ExpansionTile(
            title=ft.Text("Details"),
            affinity=ft.TileAffinity.LEADING,
            controls=[detail_content],
        )
        # Set after creation for Flet 0.85.x compatibility
        expander.initially_expanded = False

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            badge,
                            ft.Text(
                                f"Pass {result.pass_number}: "
                                f"{result.pass_name}",
                                weight=ft.FontWeight.BOLD,
                                expand=True,
                            ),
                        ]
                    ),
                    ft.Text(
                        f"{findings_count} finding(s) - {result.status}",
                        size=12,
                        color=ft.Colors.GREY_400,
                    ),
                    expander,
                ]
            ),
            padding=10,
            border=ft.Border(
                top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            ),
            border_radius=8,
            margin=ft.Margin(left=0, top=0, right=0, bottom=8),
        )

    def _export(fmt):
        report = auditData["report"]
        nb = auditData["notebook"]
        if report is None or nb is None:
            auditStatus.value = "Run an audit first."
            page.update()
            return
        cfg_settings = settings.load()
        reports_dir = cfg_settings.get(
            "reportsDir", str(defaultReportsDir())
        )
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = nb.filename.replace(".ipynb", "").replace(" ", "_")

        ext = "json" if fmt == "json" else "pdf"
        path = f"{reports_dir}/{safe_name}_{timestamp}.{ext}"
        try:
            if fmt == "json":
                to_json(report, path)
            else:
                to_pdf(report, path)
            auditStatus.value = f"Exported: {path}"
        except Exception as ex:
            auditStatus.value = f"Export error: {ex}"
        page.update()

    auditPanel = ft.Column(
        [
            ft.Text("Notebook Audit", weight=ft.FontWeight.BOLD, size=16),
            ft.Divider(),
            # Row 1: Notebooks DB scanner
            ft.Row(
                [
                    ft.ElevatedButton("Scan DB", on_click=lambda _: _scan_notebooks_db()),
                    notebookDropdown,
                ]
            ),
            # Row 2: Local path
            ft.Row(
                [
                    localPathField,
                    loadLocalBtn,
                ]
            ),
            # Row 3: GitHub URL
            ft.Row(
                [
                    githubUrlField,
                    loadBtn,
                ]
            ),
            ft.Divider(),
            ft.Text("Focus Areas:", weight=ft.FontWeight.BOLD),
            focusCheckboxes,
            ft.Divider(),
            ft.Row(
                [
                    runAuditBtn,
                    auditStatus,
                ]
            ),
            ft.Divider(),
            resultsColumn,
            ft.Divider(),
            ft.Row(
                [
                    exportPdfBtn,
                    exportJsonBtn,
                ]
            ),
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    # --- Construct Panel (R23) ---
    # Source input + source type selector + loader selector. The loader
    # selector tracks the source type 1:1 (each source type maps to exactly
    # one construct loader).
    constructSourceType = ft.Dropdown(
        label="Source type",
        options=[
            ft.DropdownOption(key="local", text="Local file"),
            ft.DropdownOption(key="github", text="GitHub"),
            ft.DropdownOption(key="http", text="HTTP URL"),
            ft.DropdownOption(key="drive", text="Google Drive"),
            ft.DropdownOption(key="kaggle", text="Kaggle dataset"),
        ],
        value="local",
        width=160,
        height=48,
        on_select=lambda e: _syncConstructLoader(),
    )
    constructLoader = ft.Dropdown(
        label="Loader",
        options=[
            ft.DropdownOption(key="load_local", text="load_local"),
            ft.DropdownOption(key="load_github", text="load_github"),
            ft.DropdownOption(key="load_http", text="load_http"),
            ft.DropdownOption(key="load_drive", text="load_drive"),
            ft.DropdownOption(key="load_kaggle", text="load_kaggle"),
        ],
        value="load_local",
        width=190,
        height=48,
        on_select=lambda e: _syncConstructSourceType(),
    )
    constructSourceInput = ft.TextField(
        label="Source",
        hint_text=_SOURCE_HINTS["local"],
        expand=True,
        height=48,
    )
    constructLoadBtn = ft.ElevatedButton("Load Source", on_click=lambda _: _loadConstructSource())
    constructSourceStatus = ft.Text("", selectable=True)

    constructScaffoldBtn = ft.ElevatedButton(
        "Scaffold",
        icon=ft.Icons.CONSTRUCTION,
        on_click=lambda _: _scaffoldConstruct(),
    )
    constructScaffoldStatus = ft.Text("", selectable=True)

    constructDraftBtn = ft.ElevatedButton(
        "Draft",
        icon=ft.Icons.PLAY_ARROW,
        on_click=lambda e: page.run_task(_runConstructDraft, e),
        bgcolor=ft.Colors.BLUE_700,
    )
    constructDraftProgress = ft.ProgressBar(value=0.0, visible=False)
    constructDraftStatus = ft.Text("", selectable=True)

    constructExportPy = ft.Checkbox(
        label="Also export flattened .py script",
        value=False,
    )
    constructExportBtn = ft.ElevatedButton(
        "Export",
        icon=ft.Icons.SAVE,
        on_click=lambda _: _exportConstruct(),
        bgcolor=ft.Colors.GREEN_700,
    )
    constructExportStatus = ft.Text("", selectable=True)
    constructExportPath = ft.Text("", selectable=True, color=ft.Colors.GREY_400)

    def _notify(message):
        page.overlay.append(ft.SnackBar(content=ft.Text(message), open=True))
        page.update()

    def _syncConstructLoader():
        constructLoader.value = _SOURCE_LOADER_MAP.get(
            constructSourceType.value, "load_local"
        )
        constructSourceInput.hint_text = _SOURCE_HINTS.get(
            constructSourceType.value, ""
        )
        page.update()

    def _syncConstructSourceType():
        reverse_map = {loader: kind for kind, loader in _SOURCE_LOADER_MAP.items()}
        constructSourceType.value = reverse_map.get(
            constructLoader.value, "local"
        )
        constructSourceInput.hint_text = _SOURCE_HINTS.get(
            constructSourceType.value, ""
        )
        page.update()

    def _loadConstructSource():
        if state.constructBusy:
            return
        raw = constructSourceInput.value.strip()
        if not raw:
            constructSourceStatus.value = "Enter a source path or URL."
            page.update()
            return
        source_type = constructSourceType.value
        if source_type == "local":
            source = loaders.load_local(raw)
        elif source_type == "github":
            source = loaders.load_github(raw)
        elif source_type == "http":
            source = loaders.load_http(raw)
        elif source_type == "drive":
            source = loaders.load_drive(raw)
        elif source_type == "kaggle":
            owner, slug = _parse_kaggle(raw)
            source = loaders.load_kaggle(owner, slug)
        else:
            source = None

        state.construct = ConstructSession(source=source)
        if source is not None and source.valid:
            constructSourceStatus.value = (
                f"Loaded: {source.filename} ({source.source}, "
                f"{len(source.content)} chars)"
            )
            constructSourceStatus.color = ft.Colors.GREEN_400
        else:
            errors = source.validation_errors if source is not None else ["Unknown source type"]
            constructSourceStatus.value = "Load failed: " + "; ".join(errors)
            constructSourceStatus.color = ft.Colors.RED_400
        page.update()

    def _scaffoldConstruct():
        if state.constructBusy:
            return
        session = state.construct
        if session is None or session.source is None or not session.source.valid:
            constructSourceStatus.value = "Load a valid source before scaffolding."
            page.update()
            return
        result = build_scaffold(session.source)
        if result.valid:
            session.scaffold = result.notebook
            constructScaffoldStatus.value = (
                f"Scaffold ready: {len(CANONICAL_HEADERS)} canonical sections "
                "with env-pin and seeds cells."
            )
            constructScaffoldStatus.color = ft.Colors.GREEN_400
        else:
            constructScaffoldStatus.value = (
                "Scaffold failed: " + "; ".join(result.validation_errors)
            )
            constructScaffoldStatus.color = ft.Colors.RED_400
        page.update()

    def _showProviderDisclosure(provider_name, cfg_snapshot):
        """External-provider disclosure (RSK-3): before any draft request to
        a non-local provider, the user must explicitly confirm that source
        content may be transmitted to that service."""

        def _confirm_disclosure(cfg_snapshot):
            page.pop_dialog()
            page.run_task(_startConstructDraft, cfg_snapshot)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("External provider disclosure"),
            content=ft.Text(
                f"Drafting will transmit the source document content to the "
                f"{provider_name} service. Do not continue if the source is "
                f"confidential. The source is used as context only; API keys "
                f"are never included in the request content."
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Continue",
                    on_click=lambda e: _confirm_disclosure(cfg_snapshot),
                ),
            ],
        )

        page.show_dialog(dlg)

    async def _runConstructDraft(e=None):
        """Entry point for the Draft button. Validates state, shows the
        external-provider disclosure when needed, then starts drafting."""
        if state.constructBusy:
            return  # busy guard: no concurrent runs (RSL-2)
        session = state.construct
        if session is None or session.source is None or not session.source.valid:
            constructSourceStatus.value = "Load a valid source before drafting."
            page.update()
            return
        if session.scaffold is None:
            constructScaffoldStatus.value = "Build the scaffold before drafting."
            page.update()
            return

        cfg_snapshot = settings.load()
        provider_name = (cfg_snapshot.get("llmProvider") or "local").strip().lower()
        # The default provider is local; the disclosure only applies to
        # external providers (openai, anthropic, ollama).
        if provider_name != "local":
            _showProviderDisclosure(provider_name, cfg_snapshot)
            return
        await _startConstructDraft(cfg_snapshot)

    async def _startConstructDraft(cfg_snapshot):
        if state.constructBusy:
            return
        state.constructBusy = True
        _setConstructBusyUi(True)
        constructDraftStatus.value = "Drafting sections ..."
        constructDraftStatus.color = ft.Colors.YELLOW_400
        constructDraftProgress.value = 0.0
        constructDraftProgress.visible = True
        page.update()

        try:
            provider = create_provider(cfg_snapshot)

            async def progress_cb(done, total, header, message):
                constructDraftProgress.value = done / total
                constructDraftStatus.value = f"[{done}/{total}] {header}: {message}"
                page.update()

            session = await draft_sections(
                state.construct.scaffold,
                state.construct.source,
                provider,
                progress_cb=progress_cb,
            )
            state.construct = session
            if session.drafted is not None:
                constructDraftStatus.value = (
                    "Draft complete: all sections drafted and validated."
                )
                constructDraftStatus.color = ft.Colors.GREEN_400
                _notify("Draft complete — ready to export.")
            else:
                constructDraftStatus.value = (
                    "Draft failed: " + "; ".join(session.errors[:4])
                )
                constructDraftStatus.color = ft.Colors.RED_400
                _notify("Drafting failed — see status.")
        except ProviderError as exc:
            constructDraftStatus.value = f"Draft error: {exc}"
            constructDraftStatus.color = ft.Colors.RED_400
            _notify("Drafting error.")
        except Exception as exc:
            # Defensive: the UI must never crash mid-run.
            constructDraftStatus.value = f"Draft error: {exc}"
            constructDraftStatus.color = ft.Colors.RED_400
        finally:
            state.constructBusy = False
            _setConstructBusyUi(False)
            constructDraftProgress.visible = False
            page.update()

    def _setConstructBusyUi(busy):
        for button in _constructButtons:
            button.disabled = busy
        page.update()

    def _exportConstruct():
        if state.constructBusy:
            return
        session = state.construct
        if session is None or session.drafted is None:
            constructDraftStatus.value = "Draft the notebook before exporting."
            page.update()
            return
        result = save_notebook(
            session.drafted,
            session.source.filename,
            export_py=constructExportPy.value,
        )
        if result.valid:
            constructExportStatus.value = "Export succeeded."
            constructExportStatus.color = ft.Colors.GREEN_400
            constructExportPath.value = f"Export path: {result.saved_path}"
            if result.py_path:
                constructExportPath.value += f"\nPython export: {result.py_path}"
            _notify(f"Notebook saved: {result.saved_path}")
        else:
            constructExportStatus.value = (
                "Export failed: " + "; ".join(result.errors)
            )
            constructExportStatus.color = ft.Colors.RED_400
        page.update()

    constructPanel = ft.Column(
        [
            ft.Text("Notebook Construction", weight=ft.FontWeight.BOLD, size=16),
            ft.Divider(),
            ft.Row([constructSourceType, constructLoader]),
            ft.Row([constructSourceInput, constructLoadBtn]),
            constructSourceStatus,
            ft.Divider(),
            ft.Row(
                [
                    constructScaffoldBtn,
                    constructScaffoldStatus,
                ]
            ),
            ft.Divider(),
            ft.Row(
                [
                    constructDraftBtn,
                    constructDraftProgress,
                ]
            ),
            constructDraftStatus,
            ft.Divider(),
            ft.Row(
                [
                    constructExportPy,
                    constructExportBtn,
                ]
            ),
            constructExportStatus,
            constructExportPath,
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    _constructButtons = [
        constructLoadBtn,
        constructScaffoldBtn,
        constructDraftBtn,
        constructExportBtn,
    ]

    # --- Tab assembly: TAB_SPEC drives both the labels and the panels ---
    panels_by_key = {
        "hardwarePanel": hardwarePanel,
        "modelsPanel": modelsPanel,
        "serverPanel": serverPanel,
        "settingsPanel": settingsPanel,
        "benchmarkPanel": benchmarkPanel,
        "auditPanel": auditPanel,
        "constructPanel": constructPanel,
    }
    panels = [panels_by_key[spec["panel"]] for spec in TAB_SPEC]

    tabs = ft.Tabs(
        selected_index=0,
        length=len(panels),
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label=spec["label"]) for spec in TAB_SPEC
                    ],
                ),
                ft.TabBarView(
                    controls=panels,
                    expand=True,
                ),
            ],
        ),
    )

    page.add(tabs)
    loadHardware()
    searchModels()
    refreshModelList()
    refreshBenchmarkModels()


def main():
    ft.run(build)
