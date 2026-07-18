# CaptainDMA board notes

These are the board paths present in the pinned `pcileech-fpga` checkout.

| Hardware label | Folder | FPGA part | XDC | Project name |
|---|---|---|---|---|
| CaptainDMA 35T FGG484 | `CaptainDMA/35t484_x1` | `xc7a35tfgg484-2` | `src/pcileech_35t484_x1_captaindma_35t.xdc` | `pcileech_35t484_x1` |
| CaptainDMA 75T FGG484 | `CaptainDMA/75t484_x1` | `xc7a75tfgg484-2` | `src/pcileech_75t484_x1_captaindma_75t.xdc` | `pcileech_75t484_x1` |
| CaptainDMA 100T FGG484 | `CaptainDMA/100t484-1` | `xc7a100tfgg484-2` | `src/pcileech_100t484_x1_captaindma_100t.xdc` | `pcileech_100t484_x1` |

The `100t484-1` directory name is part of the upstream tree; the FPGA part and generated project name are the 100T values shown above.

All three profiles use the same four core RTL files. Their SHA-256 values match at the pinned revision:

```text
src/pcileech_fifo.sv
src/pcileech_pcie_cfg_a7.sv
src/pcileech_tlps128_cfgspace_shadow.sv
src/pcileech_tlps128_bar_controller.sv
```

The board-specific differences are the part, XDC, top module, generated project name, and output BIN name. Use the source generator that belongs to the folder; do not rename a 75T project to make it fit a 100T device.

CaptainDMA's upstream hardware notes use the CH347 FPGA Tool. Keep the stock image and use the programmer path belonging to the physical board. The repository does not contain the vendor tool or a board-specific flash transcript.

## PCB files in this repository

| File | Role in this guide |
|---|---|
| `Captain35T.pcb` | 35T board design artifact; it does not select a Vivado project. |
| `Leet35T.pcb` | 35T board design artifact; it does not select a Vivado project. |
| `Stark100T.pcb` | 100T board design artifact; it does not select a Vivado project. |

There is no 75T PCB file in this repository. The 75T firmware path is the upstream `CaptainDMA/75t484_x1` project shown in the table above. The PCB files and the FPGA source checkout are separate inputs; do not infer an FPGA part from a PCB filename.
