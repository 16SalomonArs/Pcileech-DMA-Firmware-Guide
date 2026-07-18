import csv
import re
import sys
from pathlib import Path


def write_coe(path, dwords):
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write("memory_initialization_radix=16;\n")
        output.write("memory_initialization_vector=\n")
        for index, dword in enumerate(dwords):
            separator = ";\n" if index == len(dwords) - 1 else ",\n"
            output.write(f"{dword}{separator}")


def parse_offset(text, row_number):
    stripped = text.strip()
    if stripped.lower().startswith("0x"):
        stripped = stripped[2:]
    if not stripped or not re.fullmatch(r"[0-9A-Fa-f]+", stripped):
        raise ValueError(f"Invalid hexadecimal offset on CSV line {row_number}: {text}")
    offset = int(stripped, 16)
    if offset >= 4096 or offset % 4:
        raise ValueError(f"WriteMask offset must be DWORD-aligned from 0x000 to 0xFFC: 0x{offset:X}")
    return offset


def parse_mask(text, row_number):
    stripped = text.strip()
    if not re.fullmatch(r"(?:0[xX])?[0-9A-Fa-f]{8}", stripped):
        raise ValueError(f"Mask must be an 8-digit 32-bit hexadecimal value on CSV line {row_number}: {text}")
    return stripped[-8:].upper()


def build_masks(csv_path):
    dwords = ["00000000"] * 1024
    seen_offsets = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or {"offset", "mask"} - set(reader.fieldnames):
            raise ValueError("CSV must contain offset and mask columns")
        for row_number, row in enumerate(reader, start=2):
            if not row["offset"].strip() and not row["mask"].strip():
                continue
            offset = parse_offset(row["offset"], row_number)
            if offset in seen_offsets:
                raise ValueError(f"Duplicate offset in WriteMask CSV: 0x{offset:03X}")
            seen_offsets.add(offset)
            dwords[offset // 4] = parse_mask(row["mask"], row_number)
    return dwords


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 2:
        raise SystemExit("Usage: python make_writemask_coe.py writemask.csv pcileech_cfgspace_writemask.coe")

    csv_path = Path(arguments[0])
    output_path = Path(arguments[1])
    try:
        dwords = build_masks(csv_path)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    write_coe(output_path, dwords)
    print(f"Wrote {output_path}")
    for offset, value in enumerate(dwords):
        if value != "00000000":
            print(f"0x{offset * 4:03X}: {value}")


if __name__ == "__main__":
    main()
