#!/usr/bin/env python3

from pathlib import Path

import argparse
import csv
import statistics

reset = "\033[0m"
blue  = "\033[94m"

def parse_directory(dir_to_parse, cluster, writer):
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

            line_number = 0
            line_dictionary = {"system":cluster.lower(), "nodes":nodes, "cycles":num_cycles}
            for j in range(PPN_MIN_POWER, PPN_MAX_POWER+1):
                ppn = 1 << j
                print(f"Nodes {nodes}; PPN {ppn}")
                line_dictionary["ntasks"] = ppn
                for l in range(len(sizes)):
                    line_dictionary["size"] = sizes[l]
                    # MPI Advance Double Buffered Coarse
                    line_dictionary["backend"] = "MPIAdvance-CXI-Double-Buffering"
                    line_dictionary["memory_type"] = "coarse"
                    line_dictionary["send_type"] = "Ready Send"
                    line_dictionary["solver_creation"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    line_dictionary["solver_time"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    writer.writerow(line_dictionary)

                    # MPI Advance Double Buffered Fine
                    line_dictionary["memory_type"] = "fine"
                    line_dictionary["solver_creation"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    line_dictionary["solver_time"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    writer.writerow(line_dictionary)

                    # MPI Advance Single Buffered Coarse
                    line_dictionary["backend"] = "MPIAdvance-CXI-Single-Buffering"
                    line_dictionary["memory_type"] = "coarse"
                    line_dictionary["send_type"] = "Standard"
                    line_dictionary["solver_creation"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    line_dictionary["solver_time"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    writer.writerow(line_dictionary)

                    # MPI Advance Single Buffered Fine
                    line_dictionary["memory_type"] = "fine"
                    line_dictionary["solver_creation"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    line_dictionary["solver_time"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    writer.writerow(line_dictionary)

                    # Cray MPICH
                    line_dictionary["backend"] = "Cray-MPICH-CXI-GPU-Enabled"
                    line_dictionary["memory_type"] = "coarse"
                    line_dictionary["send_type"] = "Standard"
                    line_dictionary["solver_creation"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    line_dictionary["solver_time"] = lines[line_number].strip().split(": ")[-1]
                    line_number+=1
                    writer.writerow(line_dictionary)

def main():
    # CSV fields
    fieldnames = ["nodes", "ntasks", "backend",
                    "solver_creation", "solver_time", "system",
                    "size", "memory_type", "send_type", "cycles"]

    dir_to_search = Path(".")

    for entry in dir_to_search.iterdir():
        if entry.is_dir():
            device = entry.name
            data_folder = entry/"outputs"
            if(data_folder.exists()):
                outfile = f"../data/{entry.name}/scaling-data.csv"
                print(f"{blue}Found: {reset}{data_folder} - {blue}Making: {reset}{outfile}")
                with open(outfile, 'a') as output:
                    writer=csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()

                    parse_directory(data_folder, device, writer)


if __name__ == "__main__":
    main()

