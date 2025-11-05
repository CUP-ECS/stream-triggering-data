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
        "-o"
        "--outfile",
        type=str,
        required=True,
        dest="outfile",
        help="Where to store the output"
    )


    return parser.parse_args()

def parse_directory(dir_to_parse, cluster, outfile):
    for entry in dir_to_parse.iterdir():
        if entry.is_file():
            print(f"{blue}Found: {reset}{entry}")
            if "TIOGA" in entry.name:
                PPN_MAX_POWER = 3
            else:
                PPN_MAX_POWER = 2

            PPN_MIN_POWER = 0

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
                    elif "Total Simulation Time:" in line:
                        num_cycles = line.split(":")[1].strip()
            
            print(sizes)
            with open(outfile, 'a') as output:
                writer=csv.writer(output, delimiter=",")
                line_number = 0
                for j in range(PPN_MIN_POWER, PPN_MAX_POWER+1):
                    ppn = 1 << j
                    print(f"Nodes {nodes}; PPN {ppn}")
                    for l in range(len(sizes)):
                        size = sizes[l]
                        # MPI Advance Double Buffered Coarse
                        mpia_start_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        mpia_solve_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        writer.writerow([nodes, ppn, "MPIAdvance", mpia_start_time, mpia_solve_time, cluster, size, "coarse", "Ready Send", num_cycles])
                        # MPI Advance Double Buffered Fine
                        mpia_start_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        mpia_solve_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        writer.writerow([nodes, ppn, "MPIAdvance", mpia_start_time, mpia_solve_time, cluster, size, "fine", "Ready Send", num_cycles])
                        # MPI Advance Single Buffered Coarse
                        mpia_start_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        mpia_solve_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        writer.writerow([nodes, ppn, "MPIAdvance", mpia_start_time, mpia_solve_time, cluster, size, "coarse", "Standard", num_cycles])
                        # MPI Advance Single Buffered Fine
                        mpia_start_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        mpia_solve_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        writer.writerow([nodes, ppn, "MPIAdvance", mpia_start_time, mpia_solve_time, cluster, size, "fine", "Standard", num_cycles])
                        
                        # Cray MPICH
                        mpi_start_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        mpi_solve_time = lines[line_number].strip().split(": ")[-1]
                        line_number+=1
                        writer.writerow([nodes, ppn, "Cray-MPICH", mpi_start_time, mpi_solve_time, cluster, size, "coarse", "Standard", num_cycles])


def main():
    # Expects results after grep
    cmdline_options = parse_arguments()
    dir_to_search = Path(".")

    for entry in dir_to_search.iterdir():
        if entry.is_dir():
            device = entry.name
            data_folder = entry/"outputs"
            if(data_folder.exists()):
                print(f"{blue}Found: {reset}{data_folder}")
                parse_directory(data_folder, device, cmdline_options.outfile)


if __name__ == "__main__":
    main()

