#!/usr/bin/env python3
"""Build the sibling compilers into this package; never modify their checkouts."""
import os
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "toolchain"
ENV = dict(os.environ)
ENV.setdefault("LUCE_STD", str(ROOT.parent / "luce-base/src/std"))
ENV.setdefault("LUCE_CACHE", str(ROOT / "build/cache"))


def run(args, **kwargs):
    kwargs.setdefault("env", ENV)
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = ROOT.parent / "luce-base"
    luce = ROOT.parent / "luce"
    host = {("Darwin", "arm64"): "arm64-macos",
            ("Linux", "x86_64"): "x86_64-linux"}.get((platform.system(), platform.machine()))
    if not host:
        raise SystemExit("Set LUCE_BASE and LUCE to existing compilers on this host.")
    for path, pin in [(base, "BASE"), (luce, "LUCE")]:
        expected = (ROOT / "bootstrap" / pin).read_text().strip()
        actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        if actual != expected:
            raise SystemExit(f"{path}: expected {expected}, found {actual}; use explicit compiler overrides")
    run([os.environ.get("CC", "cc"), "-std=gnu11", "-O2", "-w", "-fno-strict-aliasing",
         "-I", base / "runtime", base / "bootstrap" / f"luce-base-{host}.c",
         base / "runtime" / "lucb_rt.c", "-lm", "-pthread", "-o", OUT / "stage0"])
    run([OUT / "stage0", "build", base / "src/main.lucb", "--native", "-o", OUT / "luce-base"], cwd=ROOT)
    run([OUT / "luce-base", "build", luce / "src/main.lucb", "--native", "-o", OUT / "luce"], cwd=ROOT)
    print(f"Compilers available in {OUT}")


if __name__ == "__main__":
    main()
