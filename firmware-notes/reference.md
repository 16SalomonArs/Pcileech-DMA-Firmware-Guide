# File and term reference

## Source map

| Topic | Source file |
|---|---|
| PCIe hard-IP identity, BAR, MSI, MSI-X, and DSN settings | `CaptainDMA/<profile>/ip/pcie_7x_0.xci` |
| Config shadow image | `CaptainDMA/<profile>/ip/pcileech_cfgspace.coe` |
| Config WriteMask image | `CaptainDMA/<profile>/ip/pcileech_cfgspace_writemask.coe` |
| BAR Zero4K image | `CaptainDMA/<profile>/ip/pcileech_bar_zero4k.coe` |
| Core register bank | `CaptainDMA/<profile>/src/pcileech_pcie_cfg_a7.sv` |
| USB/FIFO shadow controls | `CaptainDMA/<profile>/src/pcileech_fifo.sv` |
| Config TLP shadow | `CaptainDMA/<profile>/src/pcileech_tlps128_cfgspace_shadow.sv` |
| TLP routing and response mux | `CaptainDMA/<profile>/src/pcileech_pcie_tlp_a7.sv` |
| BAR TLP and implementations | `CaptainDMA/<profile>/src/pcileech_tlps128_bar_controller.sv` |
| PCIe core wrapper, resets, PM, and link signals | `CaptainDMA/<profile>/src/pcileech_pcie_a7.sv` |
| TLP and control interfaces | `CaptainDMA/<profile>/src/pcileech_header.svh` |
| FT601 command and TLP routing | `CaptainDMA/<profile>/src/pcileech_fifo.sv` |
| FT601/PCIe clock crossings | `CaptainDMA/<profile>/src/pcileech_com.sv`, `CaptainDMA/<profile>/src/pcileech_pcie_tlp_a7.sv` |
| FT601 output-channel mux | `CaptainDMA/<profile>/src/pcileech_mux.sv` |
| Board pins and clocks | `CaptainDMA/<profile>/src/*.xdc` |
| Project generation | `CaptainDMA/<profile>/vivado_generate_project_captaindma_*.tcl` |
| Synthesis and implementation | `CaptainDMA/<profile>/vivado_build.tcl` |

## Terms

| Term | Meaning here |
|---|---|
| BAR | Base Address Register. The PCIe core declares its size/type; the BAR controller answers MMIO requests. |
| COE | Vivado memory initialization file used by the BRAM/DROM IP. |
| DROM | Read-only memory used here for the config WriteMask. |
| DSN | PCIe Device Serial Number, driven by `ctx.cfg_dsn`. |
| DWORD | Four bytes of PCIe configuration or BAR data. |
| RO / RW / RW1C | Read-only, read/write, and read/write-one-to-clear field behavior. |
| MSI | Message Signaled Interrupt. Enabled in the checked-in PCIe XCI. |
| MSI-X | Extended MSI with a BAR-resident table and PBA. Disabled in the checked-in XCI. |
| PMCSR | Power Management Control/Status Register at the PM capability base plus `0x04`. |
| TLP | PCIe Transaction Layer Packet. |
| Byte Enable | Four lane bits carried with a DWORD write; the BAR controller passes them to `wr_be`. |
| Completion | The read response TLP assembled by the BAR read engine and returned through `tlps_bar_rsp`. |
| Requester Tag | The 8-bit field used to match a Memory Read with Cpl/CplD packets. It is unrelated to the 2-bit output-channel tags in `pcileech_mux.sv`. |
| Descriptor | A driver/device work record. The checked-in transport FIFOs do not define a descriptor format or queue ABI. |
| FLR | Function Level Reset, reported by the core as `ctx.cfg_received_func_lvl_rst`. |
| WriteMask | Per-bit selector that chooses incoming config-write data or the existing BRAM value. |
