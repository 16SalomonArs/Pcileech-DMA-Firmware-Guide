# Helper scripts

These scripts generate and check the memory images used by the CaptainDMA projects. They do not capture hardware data or create Vivado projects.

## Config-space image

Create an offset-preserving CSV from a donor capture. `coe-tools/examples/config_structure_test.csv` only checks the CSV and capability-chain format:

```csv
offset,dword
0x000,812510EC
0x004,00100006
0x008,02000005
0x02C,012310EC
0x034,00000040
0x040,00000001
0x100,00030001
```

Generate and inspect the 1024-DWORD image:

```powershell
python .\coe-tools\make_cfgspace_coe.py .\coe-tools\examples\config_structure_test.csv .\coe-tools\examples\pcileech_cfgspace.coe
python .\coe-tools\check_cfgspace_coe.py .\coe-tools\examples\pcileech_cfgspace.coe
```

The generator places each DWORD at `offset / 4`, fills unspecified locations with zero, and rejects duplicate offsets. Both `offset` and `dword` fields use hexadecimal parsing; `00000010` means `0x10`. The checker walks the standard and extended capability links, prints the Extended Capability version from bits `[19:16]`, and reports empty nodes, loops, out-of-range pointers, and unaligned pointers. PCI configuration bytes are little-endian within each DWORD. A byte sequence `EC 10 25 81` becomes `812510EC`.

## WriteMask image

Build the WriteMask from an offset/mask CSV. `coe-tools/examples/writemask_structure_test.csv` only exercises the file format; replace its rows with the offsets and masks from the donor:

```csv
offset,mask
0x004,00000007
0x03C,000000FF
```

```powershell
python .\coe-tools\make_writemask_coe.py .\coe-tools\examples\writemask_structure_test.csv .\coe-tools\examples\pcileech_cfgspace_writemask.coe
```

Unlisted DWORDs remain `00000000`, so a row must be added for every field intentionally opened by the mask. The generator rejects unaligned or out-of-range offsets, duplicate offsets, and masks that are not exactly eight hexadecimal digits.

## BAR0 image

The checked-in Zero4K implementation uses 1024 DWORDs. Generate its image from an offset/DWORD CSV:

```csv
offset,dword
0x000,12345678
0x004,00000000
0x008,ABCDEF01
```

```powershell
python .\coe-tools\make_zero4k_coe.py .\coe-tools\examples\bar0_dwords.csv .\coe-tools\examples\pcileech_bar_zero4k.coe
```

Offsets outside `0x000` through `0xFFC`, unaligned offsets, duplicate rows, and values outside 32 bits are rejected. Copy the resulting file to the selected board profile's `ip` directory before regenerating the BRAM output products.

## Source files

| Tool | Input | Output |
|---|---|---|
| `coe-tools/make_cfgspace_coe.py` | offset/DWORD CSV | `pcileech_cfgspace.coe` |
| `coe-tools/check_cfgspace_coe.py` | config COE | capability-chain report |
| `coe-tools/make_writemask_coe.py` | offset/mask CSV | `pcileech_cfgspace_writemask.coe` |
| `coe-tools/make_zero4k_coe.py` | offset/DWORD CSV | `pcileech_bar_zero4k.coe` |

Do not use the sample CSVs as donor data. `config_structure_test.csv` contains a synthetic capability chain for parser tests.

## Tests

Run the boundary tests from the repository root:

```powershell
python -m unittest discover -s coe-tools/tests -v
```
