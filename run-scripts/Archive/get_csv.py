import os
import csv
import re
import argparse

def get_time(line):
    return str(float(line.split(": ")[1]))
    
def main():
    parser = argparse.ArgumentParser(description="Create csv from tests")
    parser.add_argument("--path", type=str, default="./")
    parser.add_argument("--file", type=str, default="solver.txt")
    parser.add_argument("--system", type=str, default="N/A")
    parser.add_argument("--size", type=str, default="61440")
    parser.add_argument("--outfile", type=str, default="tests.csv")
    parser.add_argument("--memory_type", type=str, default="coarse")
    parser.add_argument("--send_type", type=str, default="N/A")
    args = parser.parse_args()
    path = args.path
    filename = args.file
    system = args.system
    size = args.size
    outfile = args.outfile
    memory_type = args.memory_type
    solve_time = 0
    create_time = 0
    cycles = 100

    with open(outfile, 'w') as csvfile:
        fieldnames = ["nodes", "ntasks", "backend", "solver_creation", "solver_time", "system", "size", "memory_type", "send_type", "cycles"]
        # add "memory_type" and "send_type"
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        with open(path+filename, 'r') as testfile:
            lines = testfile.readlines()
            lines = [line for line in lines if "Solver" in line]
            for line_num in range(len(lines)):
                if("Solver system: " in lines[line_num]):
                    system = lines[line_num].split(": ")[1].rstrip()
                if("Solver cycles: " in lines[line_num]):
                    cycles = int(lines[line_num].split(": ")[1].rstrip())
                if("Solver memory_type: " in lines[line_num]):
                    memory_type = lines[line_num].split(": ")[1].rstrip()
                if("Solver specs:" in lines[line_num]):
                    # takes all digits from filename, converts them to int and puts them in node and ntasks
                    (node, ntask) = [int(x) for x in re.findall(r'\d+', lines[line_num])]
                if("Solver backend:" in lines[line_num]):
                    backend = lines[line_num].split(": ")[1].replace(" ", "-").rstrip()
                if("Solver size:" in lines[line_num]):
                    size = lines[line_num].split("Solver size: ")[1].rstrip()

                if("Solver base:" in lines[line_num]):
                    size = lines[line_num].split("Solver base: ")[1].rstrip()
                    
                if("Solver creation" in lines[line_num]):
                    create_time = get_time(lines[line_num])
                if("Solver solve" in lines[line_num]):
                    solve_time = get_time(lines[line_num])
                if("Solver send_type: " in lines[line_num]):
                    send_type = lines[line_num].split(": ")[1].rstrip()
                    writer.writerow({"nodes":node, "ntasks":ntask, "backend":backend, "solver_creation":create_time, "solver_time":solve_time, "system":system, "size":size, "memory_type":memory_type, "send_type":send_type, "cycles":cycles})
                    solve_time=0
                    create_time=0

if __name__ == "__main__":
        main() # Call the main function when the script is run directly
