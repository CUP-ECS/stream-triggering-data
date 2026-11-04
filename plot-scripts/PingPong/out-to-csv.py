#!/usr/bin/env python3

from pathlib import Path

import argparse
import csv
import os

reset = "\033[0m"
blue  = "\033[94m"

fieldnames = ["GPU", "Backend", "Buffering", "IPC", "Iters", "Items", "Time", "Run"]

# Benchmark test name -> (Backend, Buffering), Buffering of None keeps the one from the file
test_names = {
    "st-cxi-coarse": ("cxi-coarse", None),
    "st-cxi-coarse-no-credit": ("cxi-coarse-no-credit", None),
    "st_raw-cxi-coarse": ("cxi-coarse", "raw"),
    "mpi": ("mpi", None),
    "mpi_raw": ("mpi", "raw"),
    "ipc": ("ipc", None),
}

def parse_arguments():
    parser = argparse.ArgumentParser(description="Turn bandwidth_script.sh output files into a PingPong CSV.")
    parser.add_argument("input_dir", type=Path, help="Directory of .out files from one set of runs")
    parser.add_argument("output", type=Path, help="CSV file to create (will not be overwritten)")
    parser.add_argument("--gpu", help="GPU name for every row (default: inferred from file names)")
    parser.add_argument("--skip-test", nargs="+", default=[], metavar="NAME",
                        help="Benchmark test names to leave out (e.g. st-cxi-coarse-no-credit)")
    return parser.parse_args()

def gpu_for(file_name):
    file_name = file_name.upper()
    if "TIOGA" in file_name or "FRONTIER" in file_name:
        return "MI250"
    elif "TUO" in file_name:
        return "MI300"
    raise ValueError(f"Can't infer GPU from {file_name} -- use --gpu")

def main():
    args = parse_arguments()
    if os.path.exists(args.output):
        raise SystemExit(f"{args.output} already exists -- not overwriting it")

    rows = []
    for entry in sorted(args.input_dir.glob("*.out")):
        print(f"{blue}Found: {reset}{entry}")
        gpu = args.gpu or gpu_for(entry.name)
        # e.g. tuolumne-10-16-114307.out -> 10-16-114307
        run = "-".join(entry.stem.split("-")[1:])
        test = None
        with open(entry, 'r') as file:
            for line in file:
                if line.startswith("Test:"):
                    if test is not None:
                        raise ValueError(f"{entry}: expected a time for {test}, found another test instead")
                    _, name, mode, ipc, num_iters, items = line.split()
                    test = (name, mode, ipc, num_iters, items)
                elif line.startswith("0 is done:"):
                    if test is None:
                        raise ValueError(f"{entry}: found a time with no test before it")
                    name, mode, ipc, num_iters, items = test
                    test = None
                    if name in args.skip_test:
                        continue
                    backend, buffering = test_names[name]
                    rows.append({"GPU": gpu, "Backend": backend, "Buffering": buffering or mode,
                                 "IPC": ipc, "Iters": num_iters, "Items": items,
                                 "Time": line.split(":")[1].strip(), "Run": run})
        if test is not None:
            raise ValueError(f"{entry}: {test} has no time")

    with open(args.output, 'w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.output}")

if __name__ == "__main__":
    main()
