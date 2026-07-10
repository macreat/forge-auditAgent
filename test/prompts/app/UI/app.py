"""Flet GUI for test-prompts-app.

Provides tabs for hardware info, model download, server control, and settings.
"""

import os
import flet as ft

from app.api.local import (
    checkHardware,
    haveGpuAccel,
    listAvailableModels,
    listAvailableQuantizations,
    downloadSelectedModel,
    AsyncLlamaServer,
)
from app.config import settings


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

    panels = [hardwarePanel, modelsPanel, serverPanel, settingsPanel, benchmarkPanel]

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
