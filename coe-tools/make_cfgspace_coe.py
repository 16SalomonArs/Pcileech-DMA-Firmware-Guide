import csv
import re
import sys
from pathlib import Path


def parse_hex(text, label):
    stripped = text.strip()
    if stripped.lower().startswith("0x"):
        stripped = stripped[2:]
    if not stripped or not re.fullmatch(r"[0-9A-Fa-f]+", stripped):
        raise ValueError(f"Invalid hexadecimal {label}: {text}")
    return int(stripped, 16)


def write_coe(path, dwords):
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write("memory_initialization_radix=16;\n")
        output.write("memory_initialization_vector=\n")
        for index, dword in enumerate(dwords):
            separator = ";\n" if index == len(dwords) - 1 else ",\n"
            output.write(f"{dword}{separator}")


def build_dwords(csv_path):
    dwords = ["00000000"] * 1024
    seen_offsets = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or {"offset", "dword"} - set(reader.fieldnames):
            raise ValueError("CSV must contain offset and dword columns")
        for row_number, row in enumerate(reader, start=2):
            if not row["offset"].strip() and not row["dword"].strip():
                continue
            offset = parse_hex(row["offset"], f"offset on CSV line {row_number}")
            value = parse_hex(row["dword"], f"DWORD on CSV line {row_number}")
            if offset >= 4096 or offset % 4:
                raise ValueError(f"Offset must be DWORD-aligned from 0x000 to 0xFFC: 0x{offset:X}")
            if value > 0xFFFFFFFF:
                raise ValueError(f"DWORD is outside the 32-bit range on CSV line {row_number}")
            if offset in seen_offsets:
                raise ValueError(f"Duplicate offset in CSV: 0x{offset:03X}")
            seen_offsets.add(offset)
            dwords[offset // 4] = f"{value:08X}"
    return dwords


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 2:
        raise SystemExit("Usage: python make_cfgspace_coe.py config.csv pcileech_cfgspace.coe")
    csv_path = Path(arguments[0])
    coe_path = Path(arguments[1])
    try:
        dwords = build_dwords(csv_path)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    write_coe(coe_path, dwords)
    for offset, name in ((0x000, "VID/DID"), (0x008, "Class/Revision"), (0x02C, "Subsystem IDs"), (0x034, "Capability Pointer"), (0x100, "Extended Capability Header")):
        print(f"0x{offset:03X} {name}: {dwords[offset // 4]}")
    print(f"Wrote {coe_path}")


if __name__ == "__main__":
    main()
