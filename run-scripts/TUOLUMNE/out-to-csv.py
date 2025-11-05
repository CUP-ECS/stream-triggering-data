#!/usr/bin/env python3

from pathlib import Path

import argparse
import csv
import statistics

reset = "\033[0m"
blue  = "\033[94m"

def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-d",
        "--dir",
        type=str,
        required=True,
        help="Top-level directory to look at"
    )

    parser.add_argument(
        "-o"
        "--outfile",
        type=str,
        required=True,
        dest="outfile",
        help="Where to store the output"
    )


    return parser.parse_args()

def main():
    # Expects results after grep
    cmdline_options = parse_arguments()
    dir_to_search = Path(cmdline_options.dir)

    NODES_MIN_POWER = 1
    NODES_MAX_POWER = 5
    PPN_MIN_POWER = 0
    PPN_MAX_POWER = 3
    NUM_RUNS=5

    for entry in dir_to_search.iterdir():
        if entry.is_file():
            print(f"{blue}Found: {reset}{entry}")
            if "TIOGA" in entry.name:
                device = "MI250"
            elif "TUO" in entry.name:
                device = "MI300"
            else:
                device = "?"

            nodes = entry.name.split("-")[1]
            lines = []
            sizes = []
            with open(entry, 'r') as file:
                for line in file:
                    if "Solver creation time" in line or "Solver solve time" in line:
                        lines.append(line)
                    elif "Cells" in line:
                        new_size = line.split(" ")[-4]
                        if new_size not in sizes:
                            sizes.append(new_size)
            
            print(sizes)
            with open(cmdline_options.outfile, 'a') as output:
                writer=csv.writer(output, delimiter=",")
                line_number = 0
                for j in range(PPN_MIN_POWER, PPN_MAX_POWER):
                    ppn = 1 << j
                    print(f"Nodes, {nodes}; PPN: {ppn}")
                    for k in range(NUM_RUNS):
                        for l in range(len(sizes)):
                            size = sizes[l]
                            # MPI Advance
                            mpia_start_time = lines[line_number].strip().split(": ")[-1]
                            line_number+=1
                            mpia_solve_time = lines[line_number].strip().split(": ")[-1]
                            line_number+=1
                            # print(f"A: {mpia_solve_time}")
                            # MPI
                            mpi_start_time = lines[line_number].strip().split(": ")[-1]
                            line_number+=1
                            mpi_solve_time = lines[line_number].strip().split(": ")[-1]
                            line_number+=1
                            # print(f"M: {mpi_solve_time}")

                            writer.writerow([device, "MPIAdvance", nodes, ppn, size, mpia_solve_time, mpia_start_time])
                            writer.writerow([device, "MPI", nodes, ppn, size, mpi_solve_time, mpi_start_time])


if __name__ == "__main__":
    main()

