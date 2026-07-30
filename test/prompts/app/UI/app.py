"""Flet GUI for test-prompts-app.

Provides tabs for hardware info, model download, server control, and settings.
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
from app.audit.export import to_json, to_pdf
from app.audit.pipeline import AuditPipeline
from app.config import settings
from app.config.paths import defaultReportsDir


class AppState:
    def __init__(self):
        self.server = None
        self.serverRunning = False
        self.hardware = None


state = AppState()


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
            cfg = {
                "host": serverHost.value.strip(),
                "port": int(serverPort.value),
                "nGpuLayers": int(nGpuLayers.value),
                "nCtx": int(nCtx.value),
                "modelsDir": settingsModelsDir.value.strip(),
                "lastModelPath": serverModel.value.strip(),
            }
            settings.save(cfg)
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

    panels = [hardwarePanel, modelsPanel, serverPanel, settingsPanel, benchmarkPanel, auditPanel]

    tabs = ft.Tabs(
        selected_index=0,
        length=len(panels),
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Hardware"),
                        ft.Tab(label="Models"),
                        ft.Tab(label="Server"),
                        ft.Tab(label="Settings"),
                        ft.Tab(label="Benchmark"),
                        ft.Tab(label="Audit"),
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
