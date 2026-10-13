#!/usr/bin/env python3
"""Local, bounded QEMU/OVMF firmware smoke test; does not boot either OS."""
import argparse
import hashlib
import json
import platform
import shutil
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect(config):
    qemu = shutil.which(config["qemu"])
    if not qemu:
        raise ValueError("qemu-system-x86_64 is unavailable")
    descriptor = Path(config["firmware_descriptor"])
    firmware = json.loads(descriptor.read_text())["mapping"]
    code = Path(firmware["executable"]["filename"])
    nvram = Path(firmware["nvram-template"]["filename"])
    if not code.is_file() or not nvram.is_file():
        raise ValueError("firmware descriptor references missing files")
    machines = subprocess.check_output([qemu, "-machine", "help"], text=True)
    if config["machine"] not in {line.split()[0] for line in machines.splitlines() if line.split()}:
        raise ValueError("configured machine version is not supported")
    return {
        "host": {"system": platform.system(), "architecture": platform.machine()},
        "qemu": qemu,
        "qemu_version": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0],
        "firmware_code": str(code), "firmware_vars_template": str(nvram),
        "firmware_code_sha256": digest(code), "firmware_vars_sha256": digest(nvram),
        "config": config,
        "scope": "firmware-only; Linux, AP handoff, partition UEFI and Windows remain untested",
    }


class QMP:
    def __init__(self, path, process):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        deadline = time.monotonic() + 10
        while True:
            try:
                self.sock.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.sock.close()
                    raise RuntimeError("QEMU did not expose QMP; inspect qemu.log")
                time.sleep(0.1)
        self.stream = self.sock.makefile("rwb")
        greeting = json.loads(self.stream.readline())
        if "QMP" not in greeting:
            raise RuntimeError("invalid QMP greeting")
        self.command("qmp_capabilities")

    def command(self, name, arguments=None):
        request = {"execute": name}
        if arguments:
            request["arguments"] = arguments
        self.stream.write(json.dumps(request).encode() + b"\n")
        self.stream.flush()
        while True:
            line = self.stream.readline()
            if not line:
                raise RuntimeError("QMP disconnected")
            result = json.loads(line)
            if "error" in result:
                raise RuntimeError(str(result["error"]))
            if "return" in result:
                return result["return"]

    def close(self):
        self.stream.close()
        self.sock.close()


def smoke(config, seconds):
    report = inspect(config)
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="firmware-", dir=runs))
    shutil.copyfile(report["firmware_vars_template"], run / "vars.fd")
    # Short socket path avoids macOS AF_UNIX path-length limits.
    with tempfile.TemporaryDirectory(prefix="lw-qmp-") as sockets:
        args = [report["qemu"], "-name", "linux-windows-firmware-smoke",
                "-machine", config["machine"] + ",max-ram-below-4g=2G",
                "-accel", config["accelerator"], "-cpu", config["cpu"],
                "-smp", str(config["cpus"]), "-m", str(config["memory_mib"]),
                "-drive", "if=pflash,format=raw,unit=0,readonly=on,file=" + report["firmware_code"],
                "-drive", "if=pflash,format=raw,unit=1,file=" + str(run / "vars.fd"),
                "-serial", "file:" + str(run / "serial0.log"),
                "-serial", "file:" + str(run / "serial1.log"),
                "-chardev", "file,id=fw,path=" + str(run / "firmware.log"),
                "-device", "isa-debugcon,iobase=0x402,chardev=fw",
                "-display", "none", "-vga", "std", "-net", "none",
                "-qmp", "unix:" + sockets + "/qmp,server=on,wait=off", "-no-reboot"]
        report.update({"started_utc": datetime.now(timezone.utc).isoformat(),
                       "argv": args, "observation_seconds": seconds,
                       "qemu_running": False, "uefi_shell_observed": False})
        qmp = None
        try:
            with (run / "qemu.log").open("wb") as log:
                process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
                try:
                    qmp = QMP(Path(sockets) / "qmp", process)
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError("QEMU exited before observation completed")
                        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
                    report["qmp_status"] = qmp.command("query-status")
                    report["qemu_running"] = report["qmp_status"].get("running", False)
                    report["cpus"] = qmp.command("query-cpus-fast")
                    qmp.command("screendump", {"filename": str(run / "screen.ppm")})
                    qmp.command("quit")
                    process.wait(timeout=10)
                finally:
                    if qmp:
                        qmp.close()
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                report["qemu_exit_code"] = process.returncode
            serial = (run / "serial0.log").read_text(errors="replace")
            report["uefi_shell_observed"] = "UEFI Interactive Shell" in serial and "Shell>" in serial
        except Exception as exc:
            report["error"] = str(exc)
        report["firmware_smoke_pass"] = (report["qemu_running"] and
            report["uefi_shell_observed"] and report.get("qemu_exit_code") == 0 and "error" not in report)
        (run / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"run": str(run), "firmware_smoke_pass": report["firmware_smoke_pass"],
                          "error": report.get("error"), "scope": report["scope"]}, indent=2))
        return 0 if report["firmware_smoke_pass"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight", "firmware-smoke"])
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--seconds", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error("--seconds must be between 1 and 60")
    config = json.loads(args.config.read_text())
    if args.command == "preflight":
        print(json.dumps(inspect(config), indent=2))
        return 0
    return smoke(config, args.seconds)


if __name__ == "__main__":
    raise SystemExit(main())
