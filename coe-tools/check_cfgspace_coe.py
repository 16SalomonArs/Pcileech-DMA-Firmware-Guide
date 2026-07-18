import re
import sys
from pathlib import Path


def load_dwords(path):
    text = path.read_text(encoding="ascii")
    marker = "memory_initialization_vector="
    if marker not in text:
        raise ValueError("COE is missing memory_initialization_vector")
    vector = text.split(marker, 1)[1]
    values = re.findall(r"(?m)^\s*([0-9A-Fa-f]{8})\s*[,;]\s*$", vector)
    if len(values) != 1024:
        raise ValueError(f"Expected 1024 DWORDs, found {len(values)}")
    return [value.upper() for value in values]


def value_at(dwords, offset):
    return int(dwords[offset // 4], 16)


def byte_at(dwords, offset):
    word = value_at(dwords, offset & ~3)
    return (word >> ((offset & 3) * 8)) & 0xFF


def validate_standard_pointer(pointer, label):
    if pointer < 0x40 or pointer > 0xFC:
        raise ValueError(f"Standard capability pointer out of range in {label}: 0x{pointer:02X}")
    if pointer % 4:
        raise ValueError(f"Standard capability pointer unaligned in {label}: 0x{pointer:02X}")


def validate_extended_pointer(pointer, label):
    if pointer < 0x100 or pointer >= 0x1000:
        raise ValueError(f"Extended capability pointer out of range in {label}: 0x{pointer:03X}")
    if pointer % 4:
        raise ValueError(f"Extended capability pointer unaligned in {label}: 0x{pointer:03X}")


def walk_standard_capabilities(dwords):
    pointer = byte_at(dwords, 0x34)
    if pointer == 0:
        return []
    records = []
    seen_pointers = set()
    while pointer:
        validate_standard_pointer(pointer, "capability chain")
        if pointer in seen_pointers:
            raise ValueError(f"Standard capability loop at 0x{pointer:02X}")
        seen_pointers.add(pointer)
        capability_id = byte_at(dwords, pointer)
        if capability_id == 0:
            raise ValueError(f"Empty standard capability node at 0x{pointer:02X}")
        next_pointer = byte_at(dwords, pointer + 1)
        if next_pointer:
            validate_standard_pointer(next_pointer, f"0x{pointer:02X}")
        records.append((pointer, capability_id, next_pointer))
        pointer = next_pointer
    return records


def walk_extended_capabilities(dwords):
    pointer = 0x100
    if value_at(dwords, pointer) == 0:
        return []
    records = []
    seen_pointers = set()
    while pointer:
        validate_extended_pointer(pointer, "extended capability chain")
        if pointer in seen_pointers:
            raise ValueError(f"Extended capability loop at 0x{pointer:03X}")
        seen_pointers.add(pointer)
        header = value_at(dwords, pointer)
        capability_id = header & 0xFFFF
        if capability_id == 0:
            raise ValueError(f"Empty extended capability node at 0x{pointer:03X}")
        next_pointer = (header >> 20) & 0xFFF
        if next_pointer:
            validate_extended_pointer(next_pointer, f"0x{pointer:03X}")
        version = (header >> 16) & 0xF
        records.append((pointer, capability_id, version, next_pointer))
        pointer = next_pointer
    return records


def check_coe(path):
    dwords = load_dwords(path)
    standard = walk_standard_capabilities(dwords)
    extended = walk_extended_capabilities(dwords)
    return dwords, standard, extended


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 1:
        raise SystemExit("Usage: python check_cfgspace_coe.py pcileech_cfgspace.coe")
    try:
        dwords, standard, extended = check_coe(Path(arguments[0]))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    for offset, name in ((0x000, "VID/DID"), (0x004, "Command/Status"), (0x008, "Class/Revision"), (0x02C, "Subsystem IDs"), (0x034, "Capability Pointer"), (0x100, "Extended Capability Header")):
        print(f"0x{offset:03X} {name}: {dwords[offset // 4]}")
    if standard:
        for pointer, capability_id, next_pointer in standard:
            print(f"CAP 0x{pointer:02X}: id=0x{capability_id:02X} next=0x{next_pointer:02X}")
    else:
        print("CAP chain: empty")
    if extended:
        for pointer, capability_id, version, next_pointer in extended:
            print(f"EXT 0x{pointer:03X}: id=0x{capability_id:04X} version={version} next=0x{next_pointer:03X}")
    else:
        print("EXT chain: empty")
    print("COE check completed.")


if __name__ == "__main__":
    main()
