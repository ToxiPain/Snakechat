import os
import shutil
import platform
import subprocess
from pathlib import Path
from enum import Enum
from typing import Optional
# Inicio del codigo:
WORKDIR = Path(__file__).parent
fname = "-".join(os.popen("poetry version").read().strip().split(" "))
wheel_name = f"{fname}-py3-none-any.whl"

os_name = os.environ.get("GOOS") or platform.system().lower()
arch_name = os.environ.get("GOARCH") or platform.machine().lower()
arch_name = {"aarch64": "arm64", "x86_64": "amd64"}.get(arch_name, arch_name)

print(os_name, arch_name)

class OS(Enum):
    WINDOWS = "win"
    MAC = "macosx"
    LINUX = "manylinux2014"

    @classmethod
    def auto(cls):
        if os_name == "windows":
            return cls.WINDOWS
        if os_name == "linux":
            return cls.LINUX
        if os_name == "darwin":
            return cls.MAC
        raise OSError("The binary for your operating system is not yet available. Please check back later. If you need immediate assistance, you can also contact the author of the library for support.")

class ARCH(Enum):
    AMD64 = "amd64"
    X86 = "x86"
    ARM64 = "arm64"
    ARM = "armv7l"
    AARCH64 = "aarch64"
    S390X = "s390x"
    RISCV64 = "riscv64"
    X86_64 = "x86_64"
    I386 = "i686"

    @classmethod
    def auto(cls, os: OS):
        if arch_name == "arm64":
            return cls.ARM64 if os in [OS.MAC, OS.WINDOWS] else cls.AARCH64
        if arch_name == "amd64":
            return cls.AMD64 if os == OS.WINDOWS else cls.X86_64
        if arch_name == "386":
            return cls.X86 if os == OS.WINDOWS else cls.I386
        if arch_name == "arm":
            return cls.ARM
        if arch_name == "s390x":
            return cls.S390X
        raise OSError("Unsupported architecture")

def repack(_os: OS, arch: ARCH):
    subprocess.call(["wheel", "unpack", WORKDIR / "dist" / wheel_name], cwd=WORKDIR / "dist")
    wheel_path = WORKDIR / "dist" / fname / (fname + ".dist-info") / "WHEEL"
    wheel_content = open(wheel_path, "r").read()
    arch_value = arch.value

    if _os == OS.MAC:
        arch_value = f"12_0_{arch_value}"

    with open(wheel_path, "w") as file:
        if _os == OS.WINDOWS and arch == ARCH.X86:
            new_wheel_content = wheel_content.replace("py3-none-any", "py310-none-win32")
        else:
            new_wheel_content = wheel_content.replace("py3-none-any", f"py310-none-{_os.value}_{arch_value}")

        file.write(new_wheel_content)
        print(new_wheel_content)

    subprocess.call(["wheel", "pack", WORKDIR / "dist" / fname], cwd=WORKDIR / "dist")
    os.remove(WORKDIR / "dist" / wheel_name)
    os.remove(WORKDIR / "dist" / (fname + ".tar.gz"))
    shutil.rmtree(WORKDIR / "dist" / fname)

if __name__ == "__main__":
    current_os = OS.auto()
    current_arch = ARCH.auto(current_os)
    repack(current_os, current_arch)
