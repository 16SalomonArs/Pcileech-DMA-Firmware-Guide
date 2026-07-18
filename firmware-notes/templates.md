# Record templates

## Donor record

```text
Hardware ID:
Revision / class / subsystem:
BAR0-BAR5 type, width, prefetch flag, aperture:
Standard capability offsets:
Extended capability offsets:
PM capability base / PMCSR:
MSI or MSI-X fields:
DSN:
Driver and version:
Capture tool and saved files:
```

## Build record

```text
Board profile:
FPGA part:
Vivado version:
Source commit:
Generator script:
Build script:
BIT path:
BIN path:
Timing report:
Check timing report:
BIN SHA-256:
Flash tool:
Config readback:
BAR readback:
```

## Readback comparison

```text
Offset | donor DWORD | target DWORD | result
0x000  |             |              |
0x004  |             |              |
0x008  |             |              |
0x02C  |             |              |
0x034  |             |              |
0x100  |             |              |
BAR0 + 0x000 |      |              |
BAR0 + 0x004 |      |              |
BAR0 + 0xFFC |      |              |
```
