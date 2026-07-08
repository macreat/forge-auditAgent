#checks hardware andd suggest downloadable LLMs based on system specs

import platform
import subprocess
import re
from huggingface_hub import HfApi, hf_hub_download
from config.paths import MODELS_DIR

def checkHardware():
    result = {
        "os": {},
        "systemRam": {},
        "gpu": {},
        "recommendation": {}
    }

    # ---- OS detection ----
    system = platform.system()
    isWsl = _detectWsl()
    result["os"] = {
        "platform": system,
        "isWsl": isWsl,
        "architecture": platform.machine(),
        "hostname": platform.node()
    }

    # ---- System RAM ----
    result["systemRam"] = _detectRam()

    # ---- GPU ----
    result["gpu"] = _detectGpu()

    # ---- LLM Recommendation ----
    result["recommendation"] = _makeRecommendation(result)

    return result


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


def _detectGpu():
    gpus = []

    # 1. Try GPUtil (NVIDIA, cross-platform when CUDA drivers present)
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

    # 2. Try nvidia-smi CLI
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

    # 3. Try AMD ROCm (Linux only)
    try:
        output = _runCommand(
            ["rocm-smi", "--showproductname", "--csv"]
        )
        for line in output.strip().split("\n"):
            if line.startswith("GPU") or not line.strip():
                continue
            parts = [p.strip().strip('"') for p in line.split(",")]
            if parts:
                name = parts[0] if len(parts) >= 1 else "AMD GPU"
                gpus.append({"name": name, "vramGb": None,
                             "vendor": "amd", "source": "rocm-smi"})
        if gpus:
            return {"devices": gpus, "primary": gpus[0]}
    except Exception:
        pass

    # 4. Try macOS system_profiler
    system = platform.system()
    if system == "Darwin":
        try:
            output = _runCommand(
                ["system_profiler", "SPDisplaysDataType"]
            )
            for line in output.split("\n"):
                m = re.search(r"Chipset Model:\s+(.+)", line)
                if m:
                    gpus.append({"name": m.group(1).strip(), "vramGb": None,
                                 "vendor": "apple", "source": "system_profiler"})
            if gpus:
                return {"devices": gpus, "primary": gpus[0]}
        except Exception:
            pass

    # 5. Fallback: try lspci (Linux), wmic (Windows)
    try:
        if system == "Linux":
            output = _runCommand(["lspci"])
            for line in output.split("\n"):
                if "VGA" in line or "3D" in line:
                    gpus.append({"name": line.strip(), "vramGb": None,
                                 "vendor": "unknown", "source": "lspci"})
        elif system == "Windows":
            output = _runCommand(
                ["wmic", "path", "win32_VideoController", "get", "Name"]
            )
            for line in output.strip().split("\n")[1:]:
                if line.strip():
                    gpus.append({"name": line.strip(), "vramGb": None,
                                 "vendor": "unknown", "source": "wmic"})
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
        local_dir=str(MODELS_DIR)
    )