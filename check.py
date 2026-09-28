#!/usr/bin/env python3
"""Previous Paris-only entry point.

Runs the Fransa / Paris Başkonsolosluğu check through tvc.py.
Prefer tvc.py for any other consulate.
"""

from __future__ import annotations

import sys

import tvc


def legacy_argv(argv: list[str]) -> list[str]:
    mode = "check"
    interval = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--loop":
            mode = "watch"
        elif arg == "--install":
            mode = "install"
        elif arg == "--interval-hours":
            index += 1
            if index >= len(argv):
                raise ValueError("--interval-hours needs a number of hours")
            interval = argv[index]
        elif arg.startswith("--interval-hours="):
            interval = arg.split("=", 1)[1]
        else:
            raise ValueError(f"unknown argument {arg}. See python3 tvc.py --help")
        index += 1
    command = [mode, "france", "paris"]
    if mode == "check":
        command.append("--notify")
    if interval is not None and mode != "check":
        number = interval[:-1] if interval.lower().endswith("h") else interval
        command.extend(["--interval", f"{number}h"])
    return command


def main() -> int:
    if sys.argv[1:] in (["-h"], ["--help"]):
        print(__doc__.strip())
        print("\npython3 check.py              check Paris once and notify on a new date")
        print("python3 check.py --loop       keep checking Paris")
        print("python3 check.py --install    install the macOS schedule for Paris")
        return 0
    try:
        argv = legacy_argv(sys.argv[1:])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return tvc.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
