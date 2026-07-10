#!/usr/bin/env python3
"""Cross-platform installer for test-prompts-app with GPU acceleration.

Detects the available GPU backend (Metal, CUDA, ROCm, or CPU), creates a
Python virtual environment, and installs all dependencies including
``llama-cpp-python[server]`` compiled with the appropriate backend flags.

Can be run directly from source or compiled into a PyInstaller one-file
executable for distribution.

Usage:
    python3 scripts/install.py [TARGET_DIR]

    TARGET_DIR — where to create the venv (defaults to current directory).
"""

import platform
import subprocess
import sys
import os
import shutil
import glob


def isPyinstallerBundle():
    """Return ``True`` if running inside a PyInstaller one-file bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resourcePath(relativePath):
    """Get the absolute path to a resource, works in dev and PyInstaller.

    Args:
        relativePath (str): Path relative to the project root.

    Returns:
        str: Absolute path to the resource.
    """
    if isPyinstallerBundle():
        return os.path.join(sys._MEIPASS, relativePath)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relativePath)


def findSystemPython():
    """Find a usable system Python interpreter.

    When running as a PyInstaller bundle, ``sys.executable`` points to the
    bundled executable, not a real Python interpreter capable of creating
    venvs or running ``pip install``. This function searches ``$PATH`` for
    ``python3`` or ``python``.

    Returns:
        str: Path to a system Python interpreter.

    Raises:
        SystemExit: If no suitable Python is found.
    """
    candidates = ["python3", "python"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            try:
                version = subprocess.check_output(
                    [path, "--version"], text=True, stderr=subprocess.STDOUT
                ).strip()
                print(f"Using system Python: {path} ({version})")
                return path
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
    sys.exit("ERROR: Could not find a system Python interpreter (python3/python) on PATH.")


def detectBackend():
    """Determine which GPU acceleration backend is available.

    Returns:
        str: One of ``"metal"``, ``"cuda"``, ``"rocm"``, or ``"cpu"``.
    """
    system = platform.system()
    if system == "Darwin":
        return "metal"
    try:
        subprocess.check_output(["nvidia-smi"], text=True, stderr=subprocess.DEVNULL)
        if shutil.which("nvcc"):
            return "cuda"
        print("WARNING: nvidia-smi found but nvcc (CUDA Toolkit) is not installed.")
        print("  Install the CUDA Toolkit or run with CPU-only mode.")
        print("  Falling back to CPU mode.")
        return "cpu"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if system == "Linux":
        try:
            subprocess.check_output(["rocm-smi"], text=True, stderr=subprocess.DEVNULL)
            if shutil.which("hipcc") or shutil.which("nvcc"):
                return "rocm"
            print("WARNING: rocm-smi found but HIP compiler is not installed.")
            print("  Install the ROCm toolkit or run with CPU-only mode.")
            print("  Falling back to CPU mode.")
            return "cpu"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    return "cpu"


def install(targetDir=None):
    """Create venv and install all dependencies with GPU acceleration.

    Args:
        targetDir (str | None): Directory where the venv will be created.
            Defaults to the current working directory.
    """
    if targetDir is None:
        targetDir = os.getcwd()

    targetDir = os.path.abspath(targetDir)
    os.makedirs(targetDir, exist_ok=True)

    venvDir = os.path.join(targetDir, "venv")
    requirementsPath = resourcePath("requirements.txt")

    python = sys.executable if not isPyinstallerBundle() else findSystemPython()

    backend = detectBackend()
    print(f"Detected GPU backend: {backend}")

    cmakeArgsMap = {
        "cuda": "-DGGML_CUDA=ON",
        "rocm": "-DGGML_HIPBLAS=ON",
        "metal": "-DGGML_METAL=ON",
        "cpu": "",
    }
    cmakeArgs = cmakeArgsMap[backend]

    print(f"Creating virtual environment in {venvDir} ...")
    subprocess.check_call([python, "-m", "venv", venvDir])

    pip = os.path.join(venvDir, "bin", "pip") if platform.system() != "Windows" \
        else os.path.join(venvDir, "Scripts", "pip.exe")

    print("Installing base dependencies ...")
    subprocess.check_call([pip, "install", "-r", requirementsPath])

    env = os.environ.copy()
    if cmakeArgs:
        env["CMAKE_ARGS"] = cmakeArgs
    else:
        env.pop("CMAKE_ARGS", None)

    print(f"Installing llama-cpp-python[server] with CMAKE_ARGS=\"{cmakeArgs or '(none)'}\" ...")
    subprocess.check_call(
        [pip, "install", "llama-cpp-python[server]", "--force-reinstall", "--no-cache-dir"],
        env=env,
    )

    venvPython = os.path.join(venvDir, "bin", "python3") if platform.system() != "Windows" \
        else os.path.join(venvDir, "Scripts", "python.exe")

    print("\n" + "=" * 60)
    print("Installation complete!")
    print("=" * 60)
    print(f"\nVenv created at: {venvDir}")
    print(f"GPU backend:     {backend}")
    print(f"\nRun the app:")
    print(f"  {venvPython} app/main.py")
    if backend != "cpu":
        print(f"\nUse nGpuLayers=-1 in AsyncLlamaServer for full GPU offload.")
    else:
        print(f"Use nGpuLayers=0 in AsyncLlamaServer for CPU-only mode.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    install(target)
