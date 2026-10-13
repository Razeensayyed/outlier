"""Usage: python -m 100DAP {init,run} [options]"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback


def cmd_init() -> None:
    print("100DAP initialized. Configure your 100-day plan before the first run.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="100DAP")
    parser.add_argument("job", choices=["init", "run"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        {
            "init": cmd_init,
        }.get(args.job, lambda: None)()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
