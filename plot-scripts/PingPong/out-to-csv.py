#!/usr/bin/env python3
"""Turn packing ping-pong output files into a PingPong CSV.

    out-to-csv.py <run dir or .out files...> <output.csv> [--gpu NAME] [--skip-test NAME...]

Reads run-scripts/pingpong-job.sh output, and the older output of stream-triggering's
tests/benchmark/bandwidth_script.sh. Columns: GPU,Backend,Buffering,IPC,Iters,Items,Time,Run
(Time is seconds for all Iters round trips of Items ints; Run is the file name without its
leading system name). Runs that failed or never finished are reported and left out.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdcommon as sd  # noqa: E402

FIELDS = ["GPU", "Backend", "Buffering", "IPC", "Iters", "Items", "Time", "Run"]

# Benchmark test name -> (Backend, Buffering); Buffering None keeps the run's own sb/db
TESTS = {
    "st-cxi-coarse": ("cxi-coarse", None),
    "st-cxi-fine": ("cxi-fine", None),
    "st-cxi-coarse-no-credit": ("cxi-coarse-no-credit", None),
    "st_raw-cxi-coarse": ("cxi-coarse", "raw"),
    "mpi": ("mpi", None),
    "mpi_raw": ("mpi", "raw"),
    "ipc": ("ipc", None),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="run directories or .out files, then the CSV to write")
    parser.add_argument("--gpu", help="GPU name for every row (default: from the file names)")
    parser.add_argument("--skip-test", nargs="+", default=[], metavar="NAME",
                        help="benchmark test names to leave out (e.g. st-cxi-coarse-no-credit)")
    args = parser.parse_args()
    if len(args.inputs) < 2:
        parser.error("need at least one input and the output CSV")
    *inputs, output = args.inputs

    rows, failed = [], 0
    for path in sd.out_files(inputs):
        sd.log(f"reading {path}")
        gpu = args.gpu or sd.GPU[sd.system_of(path)]
        run = "-".join(path.stem.split("-")[1:])
        for fields, body, code in sd.runs(path):
            name, mode, ipc, iters, items = fields
            if name in args.skip_test:
                continue
            if name not in TESTS:
                raise SystemExit(f"{path}: unknown test '{name}' (known: {', '.join(TESTS)}); "
                                 "add it to TESTS or pass --skip-test")
            times = [line.split(":", 1)[1].strip() for line in body if line.startswith("0 is done:")]
            if code not in (0, None) or len(times) != 1:
                sd.warn(f"{path.name}: {' '.join(fields)} -- exit {code}, {len(times)} time(s): left out")
                failed += 1
                continue
            backend, buffering = TESTS[name]
            rows.append({"GPU": gpu, "Backend": backend, "Buffering": buffering or mode, "IPC": ipc,
                         "Iters": iters, "Items": items, "Time": times[0], "Run": run})
    sd.write_csv(output, FIELDS, rows)
    if failed:
        sd.warn(f"{failed} run(s) left out")


if __name__ == "__main__":
    main()
