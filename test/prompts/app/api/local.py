"""Hardware detection, HuggingFace model discovery, and local LLM server.

Provides functions to detect OS, RAM, and GPU hardware, query HuggingFace
for compatible GGUF models, download selected models, and run a local
inference server via :mod:`llama_cpp`.

Backend support (multi-OS):
    - **CUDA** — NVIDIA GPUs on Linux / Windows
    - **ROCm** — AMD GPUs on Linux
    - **Metal** — Apple Silicon / Intel on macOS
"""

import platform
import subprocess
import re
import asyncio
from huggingface_hub import HfApi, hf_hub_download
from app.config.paths import MODELS_DIR, defaultModelsDir

def checkHardware():
    """Check the local system hardware and return a summary dict.

    Returns:
        dict: Keys ``os``, ``systemRam``, ``gpu``, ``recommendation``.
            See :func:`_detectRam`, :func:`_detectGpu`, and
            :func:`_makeRecommendation` for sub-structure details.
    """
    result = {
        "os": {},
        "systemRam": {},
        "gpu": {},
        "recommendation": {}
    }

    system = platform.system()
    isWsl = _detectWsl()
    result["os"] = {
        "platform": system,
        "isWsl": isWsl,
        "architecture": platform.machine(),
        "hostname": platform.node()
    }

    result["systemRam"] = _detectRam()

    gpuAccelAvailable = haveGpuAccel()
    totalRamGb = result["systemRam"].get("totalGb", 0)
    if gpuAccelAvailable:
        result["gpu"] = _detectGpu(totalRamGb)
    else:
        result["gpu"] = {"devices": [], "primary": None, "gpuAccelAvailable": False}

    result["recommendation"] = _makeRecommendation(result)

    return result

def haveGpuAccel():
    """Detect whether any GPU acceleration backend is available.

    Checks for Metal (macOS), CUDA (nvidia-smi), or ROCm (rocm-smi).

    Returns:
        bool: ``True`` if a supported GPU backend was detected.
    """
    system = platform.system()
    if system == "Darwin":
        return True
    try:
        subprocess.check_output(["nvidia-smi"], text=True, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if system == "Linux":
        try:
            subprocess.check_output(["rocm-smi"], text=True, stderr=subprocess.DEVNULL)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    return False

def _detectWsl():
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _detectRam():
    try:
        import psutil
        ram = psutil.virtual_memory()
        return {
            "totalGb": round(ram.total / (1024 ** 3), 2),
            "availableGb": round(ram.available / (1024 ** 3), 2),
            "usedPercent": ram.percent
        }
    except ImportError:
        return {"totalGb": 0, "availableGb": 0, "usedPercent": 0,
                "error": "psutil not installed"}


def _detectGpu(totalRamGb=0):
    """Enumerate GPUs available for acceleration.

    Detection order:
        - macOS: ``system_profiler SPDisplaysDataType`` (Metal)
        - GPUtil (NVIDIA)
        - nvidia-smi CLI (NVIDIA)
        - rocm-smi CLI (AMD)

    Args:
        totalRamGb (float): Total system RAM in GiB. Used as VRAM on
            Apple Silicon (unified memory).

    Returns:
        dict: ``{"devices": [...], "primary": {...}|None}`` where each
        device has keys ``name``, ``vramGb``, ``vendor``, ``source``.
    """

    gpus = []
    system = platform.system()
    if system == "Darwin":
        try:
            output = _runCommand(
                ["system_profiler", "SPDisplaysDataType"]
            )
            for line in output.split("\n"):
                m = re.search(r"Chipset Model:\s+(.+)", line)
                if m:
                    gpus.append({
                        "name": m.group(1).strip(),
                        "vramGb": totalRamGb,
                        "vendor": "apple",
                        "source": "system_profiler"
                    })
            if gpus:
                return {"devices": gpus, "primary": gpus[0]}
        except Exception:
            pass
        return {"devices": [], "primary": None}

    try:
        import GPUtil
        for g in GPUtil.getGPUs():
            gpus.append({
                "name": g.name.strip(),
                "vramGb": round(g.memoryTotal / 1024, 2),
                "vendor": "nvidia",
                "source": "GPUtil"
            })
        if gpus:
            return {"devices": gpus, "primary": gpus[0]}
    except Exception:
        pass

    try:
        output = _runCommand(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"]
        )
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                name = parts[0]
                vramMb = float(parts[1].strip().split()[0]) if parts[1].strip() else 0
                gpus.append({
                    "name": name,
                    "vramGb": round(vramMb / 1024, 2),
                    "vendor": "nvidia",
                    "source": "nvidia-smi"
                })
        if gpus:
            return {"devices": gpus, "primary": gpus[0]}
    except Exception:
        pass

    try:
        output = _runCommand(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--csv"]
        )
        lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            raise ValueError("no GPU rows")
        headerLine = [p.strip().strip('"') for p in lines[0].split(",")]
        nameIdx = next((i for i, h in enumerate(headerLine) if "product" in h.lower() or "name" in h.lower()), 0)
        vramIdx = next((i for i, h in enumerate(headerLine) if "vram" in h.lower() or "mem" in h.lower()), None)
        for line in lines[1:]:
            parts = [p.strip().strip('"') for p in line.split(",")]
            name = parts[nameIdx] if nameIdx < len(parts) else "AMD GPU"
            vramGb = None
            if vramIdx is not None and vramIdx < len(parts) and parts[vramIdx]:
                vramGb = round(float(parts[vramIdx]) / (1024 ** 3), 2)
            gpus.append({
                "name": name,
                "vramGb": vramGb,
                "vendor": "amd",
                "source": "rocm-smi"
            })
        if gpus:
            return {"devices": gpus, "primary": gpus[0]}
    except Exception:
        pass

    return {"devices": [], "primary": None}


def _runCommand(cmd):
    return subprocess.check_output(
        cmd, stderr=subprocess.DEVNULL, timeout=10
    ).decode("utf-8", errors="replace")


def _makeRecommendation(result):
    """Suggest a model parameter-size ceiling based on hardware.

    Uses GPU VRAM when available, otherwise falls back to system RAM.

    Args:
        result (dict): The full hardware dict produced by
            :func:`checkHardware`.

    Returns:
        dict: ``{"size": float, "mode": str}`` where ``size`` is the
        recommended max parameter count in bytes and ``mode`` is
        ``"gpu"`` or ``"cpu"``.
    """
    ram = result["systemRam"]
    availableRamGb = ram.get("availableGb", 0)
    totalRamGb = ram.get("totalGb", 0)

    gpu = result.get("gpu", {})
    primary = gpu.get("primary") if gpu else None
    hasGpu = primary is not None and primary.get("vramGb") is not None
    vramGb = primary["vramGb"] if hasGpu else 0

    if hasGpu and vramGb > 0:
        if vramGb >= 16:
            recommendation = {
                "size": 32e9,
                "mode": "gpu"
            }
        elif vramGb >= 8:
            recommendation = {
                "size": 8e9,
                "mode": "gpu"
            }
        elif vramGb >= 4:
            recommendation = {
                "size": 3e9,
                "mode": "gpu"
            }
        else:
            recommendation = {
                "size": 1.5e9,
                "mode": "gpu"
            }
    else:
        if availableRamGb >= 24 or totalRamGb >= 32:
            recommendation = {
                "size": 8e9,
                "mode": "cpu"
            }
        elif availableRamGb >= 12 or totalRamGb >= 16:
            recommendation = {
                "size": 4e9,
                "mode": "cpu"
            }
        else:
            recommendation = {
                "size": 1.5e9,
                "mode": "cpu"
            }

    return recommendation

def listAvailableModels(recommendationDict):
    """Query HuggingFace for GGUF text-generation models within size limits.

    Args:
        recommendationDict (dict): Output of :func:`checkHardware`.

    Returns:
        list[str]: HuggingFace model IDs (e.g. ``"org/repo"``).
    """
    maxModelSize = recommendationDict["recommendation"]["size"]

    api = HfApi()

    models = api.list_models(
        filter="text-generation",
        cardData=True,
        limit=200
    )

    filtered_models = []

    for model in models:
        m = re.search(r"[-_](\d+\.?\d*)([BM])", model.modelId)
        if not m:
            continue
        val = float(m.group(1))
        unit = m.group(2).upper()
        param_count = val * 1e9 if unit == "B" else val * 1e6

        if param_count > 50_000_000 and param_count <= maxModelSize and any("gguf" in t.lower() for t in (model.tags or [])):
            filtered_models.append(model.modelId)

    return filtered_models

def listAvailableQuantizations(modelId):
    """List GGUF quantization variants and their sizes for a model.

    Args:
        modelId (str): HuggingFace model ID (``org/repo``).

    Returns:
        dict[str, float]: Quantization name → file size in MiB.
    """
    api = HfApi()
    files = api.list_repo_files(repo_id=modelId)
    gguFs = sorted(f for f in files if f.endswith(".gguf"))
    if not gguFs:
        return {}
    infos = api.get_paths_info(repo_id=modelId, paths=gguFs)
    result = {}
    for info in infos:
        m = re.search(r"-([^/]+)\.gguf$", info.path)
        if m:
            quant = m.group(1)
            result[quant] = round(info.size / (1024 * 1024), 1)
    return result

def downloadSelectedModel(modelId, quantization):
    """Download a single GGUF file for the given model and quantization.

    Args:
        modelId (str): HuggingFace model ID.
        quantization (str): Quantization tag (e.g. ``"Q4_K_M"``).

    Returns:
        str: Local path to the downloaded ``.gguf`` file.

    Raises:
        ValueError: If the quantization is not found in the repository.
    """
    api = HfApi()
    files = api.list_repo_files(repo_id=modelId)
    match = None
    for f in files:
        if f.endswith(f"-{quantization}.gguf"):
            match = f
            break
    if not match:
        raise ValueError(f"Quantization '{quantization}' not found in {modelId}")
    return hf_hub_download(
        repo_id=modelId,
        filename=match,
        local_dir=str(defaultModelsDir())
    )


class AsyncLlamaServer:
    """In-process local LLM server using :mod:`llama_cpp` and :mod:`uvicorn`.

    Wraps ``llama-cpp-python[server]`` to serve a GGUF model via an
    OpenAI-compatible HTTP API without spawning a separate process.

    Args:
        modelPath (str): Absolute path to the ``.gguf`` model file.
        host (str): Bind address. Default ``"127.0.0.1"``.
        port (int): Listen port (1–65535). Default ``8000``.
        nGpuLayers (int): Layers to offload to GPU. ``-1`` for all,
            ``0`` for CPU-only. Default ``0``.
        nCtx (int): Context window size in tokens. Default ``2048``.

    Example:
        >>> server = AsyncLlamaServer("/path/to/model.gguf", nGpuLayers=-1)
        >>> await server.start()
        >>> # server is now serving at http://127.0.0.1:8000
        >>> await server.stop()
    """
    def __init__(self, modelPath, host="127.0.0.1", port=8000, nGpuLayers=0, nCtx=2048):
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"Invalid port: {port}")
        self.modelPath = modelPath
        self.host = host
        self.port = port
        self.nGpuLayers = nGpuLayers
        self.nCtx = nCtx
        self._server = None
        self._task = None

    async def start(self):
        from llama_cpp.server.app import create_app
        from llama_cpp.server.settings import ModelSettings, ServerSettings
        import uvicorn

        modelSettings = ModelSettings(
            model=self.modelPath,
            n_ctx=self.nCtx,
            n_gpu_layers=self.nGpuLayers
        )
        serverSettings = ServerSettings(
            host=self.host,
            port=self.port
        )
        app = create_app(
            server_settings=serverSettings,
            model_settings=[modelSettings]
        )
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())

    async def stop(self):
        if self._server:
            self._server.should_exit = True
            if self._task:
                await self._task
            self._server = None
            self._task = None
