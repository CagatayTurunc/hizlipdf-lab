"""Linux bubblewrap profiles. Missing support must fail closed, never emulate success."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

PROFILES = {
    "A": {"name": "Geniş laboratuvar yetkisi", "files": True, "network": True},
    "B": {"name": "Dosya erişimi dar", "files": False, "network": True},
    "C": {"name": "Ağ bağlantısı kapalı", "files": True, "network": False},
    "D": {"name": "Dosya ve ağ kısıtlı", "files": False, "network": False},
}


def capability():
    if platform.system() != "Linux":
        return {"available": False, "reason": "Gerçek B/C/D izolasyonu Linux ve bubblewrap gerektirir. Bu ortamda yalnızca A çalışır."}
    binary = shutil.which("bwrap")
    if not binary:
        return {"available": False, "reason": "bubblewrap bulunamadı; kısıtlı profiller devre dışı."}
    try:
        check = subprocess.run([binary, "--ro-bind", "/", "/", "--unshare-user", "--unshare-net", "--", "/bin/true"],
                               capture_output=True, timeout=5)
        if check.returncode:
            return {"available": False, "reason": "Linux kullanıcı/ağ alanı oluşturulamıyor; kısıtlı profiller devre dışı."}
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "reason": "bubblewrap kullanılabilirliği doğrulanamadı."}
    return {"available": True, "reason": "Linux bubblewrap hazır. Profil sonuçları deneyle doğrulanmalıdır."}


def command(config, config_path, run_dir, root, supported):
    if config["profile"] not in PROFILES:
        raise ValueError("Unknown profile")
    if not supported:
        if config["profile"] != "A":
            raise ValueError("Requested isolation is unavailable")
        return [sys.executable, str(root / "worker.py"), str(config_path)]
    # The supported target is a minimal Linux lab/VM with system-installed Python/LibreOffice.
    # No host home, project evidence, /etc secrets or application server are mounted.
    cmd = [shutil.which("bwrap"), "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid",
           "--unshare-ipc", "--unshare-uts", "--cap-drop", "ALL", "--proc", "/proc", "--dev", "/dev",
           "--tmpfs", "/tmp", "--dir", "/etc", "--dir", "/lab", "--dir", "/lab/targets"]
    if not PROFILES[config["profile"]]["network"]:
        cmd += ["--unshare-net"]
    for system in ("/usr", "/bin", "/lib", "/lib64", "/sbin"):
        if Path(system).exists():
            cmd += ["--ro-bind", system, system]
    for item in ("/etc/fonts", "/etc/ld.so.cache", "/etc/alternatives", "/etc/passwd", "/etc/group"):
        if Path(item).exists():
            cmd += ["--ro-bind", item, item]
    cmd += ["--ro-bind", str(root), "/app", "--ro-bind", str(run_dir / "plugin.zip"), "/lab/plugin.zip",
            "--ro-bind", str(run_dir / "input.docx"), "/lab/input.docx",
            "--ro-bind", str(config_path), "/lab/config.json", "--bind", str(run_dir / "output"), "/lab/output",
            "--bind", str(run_dir / "home"), "/lab/home", "--chdir", "/lab"]
    if PROFILES[config["profile"]]["files"]:
        cmd += ["--ro-bind", str(run_dir / "targets"), "/lab/targets"]
    cmd += ["--setenv", "HOME", "/lab/home", "--setenv", "TMPDIR", "/tmp", "--",
            "/usr/bin/python3", "/app/worker.py", "/lab/config.json"]
    return cmd
