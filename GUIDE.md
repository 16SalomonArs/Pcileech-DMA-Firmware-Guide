# PCILeech FPGA Firmware Customization Guide

## 1. Environment and tools

Use a normal Windows 10 or Windows 11 x64 installation with Git, Python 3, and Vivado 2023.2. The 35T and 75T XCI metadata records Vivado `2023.2`; the 100T project records the `2023.2.2` patch level.

Clone the source and pin the revision before changing a board project:

```powershell
git clone https://github.com/ufrisk/pcileech-fpga.git C:\pcileech-fpga
git -C C:\pcileech-fpga checkout c538c4170678c13f723dc921905fb81ff3c71d8e
git -C C:\pcileech-fpga rev-parse HEAD
```

Check the local tools from PowerShell:

```powershell
& "C:\Xilinx\Vivado\2023.2\bin\vivado.bat" -version
git --version
python --version
```

Keep paths short. `C:\pcileech-fpga` avoids quoting problems in exported Vivado Tcl and generated IP paths.

## 2. Board and recovery preparation

The board directory fixes the FPGA part, package, XDC, top module, project name, and output name. Do not move constraints or generated IP between profiles.

| Board profile | Upstream directory | FPGA part | Project generator | Build script |
|---|---|---|---|---|
| CaptainDMA 35T FGG484 | `CaptainDMA/35t484_x1` | `xc7a35tfgg484-2` | `vivado_generate_project_captaindma_35t.tcl` | `vivado_build.tcl` |
| CaptainDMA 75T FGG484 | `CaptainDMA/75t484_x1` | `xc7a75tfgg484-2` | `vivado_generate_project_captaindma_75t.tcl` | `vivado_build.tcl` |
| CaptainDMA 100T FGG484 | `CaptainDMA/100t484-1` | `xc7a100tfgg484-2` | `vivado_generate_project_captaindma_100t.tcl` | `vivado_build.tcl` |

Before changing the image, keep the stock firmware for the exact board and confirm that the CH347 programmer can see the update interface. The CaptainDMA upstream instructions use the WCH CH347 FPGA Tool for these board families. M.2 variants require the matching M2-FW adapter and its documented orientation.

## 3. Donor information capture

Record the donor before editing the PCIe IP. At minimum, save:

- vendor, device, subsystem, revision, and class code;
- BAR type, width, prefetch flag, and aperture size for BAR0 through BAR5;
- the standard capability chain from the pointer at `0x34`;
- the extended capability chain starting at `0x100`;
- MSI layout, DSN, and the PM capability offset;
- driver name and version;
- config-space and BAR readback from the same device state.

Device Manager supplies the instance ID, hardware IDs, driver details, and allocated resources. PowerShell can preserve the property set:

```powershell
$InstanceId = 'PCI\VEN_xxxx&DEV_xxxx&SUBSYS_xxxxxxxx&REV_xx\INSTANCE'
Get-PnpDeviceProperty -InstanceId $InstanceId |
    Sort-Object KeyName |
    Format-List KeyName,Data
```

Use Arbor, TeleScan PE, or another PCI configuration viewer for offset-preserving config-space capture. A Windows resource address is the address assigned for that boot; it is not the BAR aperture size and must not be copied into a static COE.

## 4. PCIe Core parameters

Open `ip/pcie_7x_0.xci` through Vivado's **Customize IP** action. Change the identity and BAR declarations there, then regenerate output products.

The checked-in CaptainDMA profiles start with these values:

| Field | Value in the pinned source |
|---|---|
| Link | Gen2 x1, 64-bit user interface, 62.5 MHz user clock |
| Identity | `10EE:0666`, subsystem `10EE:0007`, revision `02` |
| Class | `020000` Ethernet controller |
| BAR0 | 4 KB, 32-bit memory, non-prefetchable |
| BAR1-BAR5 | disabled |
| MSI | enabled, one vector, 64-bit address capable |
| MSI-X | disabled |
| DSN capability | enabled |

Keep the XCI BAR declaration aligned with the RTL instance selected in `src/pcileech_tlps128_bar_controller.sv`. A 64-bit BAR consumes two BAR slots. BAR sizing belongs to the PCIe core; BAR read and write behavior belongs to the RTL.

## 5. Configuration space

The shadow image is `ip/pcileech_cfgspace.coe`. The attached BRAM is 32 bits wide and 1024 DWORDs deep, so the image covers 4096 bytes.

Build the image from offset-tagged DWORDs rather than pasted rows. Use `coe-tools/examples/config_structure_test.csv` to check the input format; pass the donor CSV when generating a board image:

```powershell
python .\coe-tools\make_cfgspace_coe.py .\coe-tools\examples\config_structure_test.csv .\coe-tools\examples\pcileech_cfgspace.coe
python .\coe-tools\check_cfgspace_coe.py .\coe-tools\examples\pcileech_cfgspace.coe
```

CSV format:

```csv
offset,dword
0x000,812510EC
0x008,02000005
0x02C,012310EC
0x034,00000040
0x040,00000001
0x100,00030001
```

The values above are format examples only. Replace them with the DWORDs from the donor capture.

The CSV parser treats every `dword` field as hexadecimal, with or without a `0x` prefix. `00000010` therefore means `0x10`, not decimal 10. Each DWORD is stored as the 32-bit little-endian value. For config bytes `EC 10 25 81` at offset `0x00`, the COE DWORD is `812510EC`.

Review `0x00`, `0x04`, `0x08`, `0x2C`, `0x34`, and `0x100`, then walk both capability chains. A nonzero standard capability pointer must identify a nonzero, DWORD-aligned node from `0x40` through `0xFC`. A nonzero extended pointer must be DWORD-aligned from `0x100` through `0xFFC`; the checker also prints the version from header bits `[19:16]`. It reports an empty node, loop, out-of-range pointer, or unaligned pointer before Vivado reads the image. Replace the COE in the selected board's `ip` directory before generating the project.

## 6. Shadow Config

The shadow path is controlled in `src/pcileech_fifo.sv`:

```systemverilog
rw[202] <= 1'b1; // configuration TLP processing
rw[203] <= 1'b0; // return BRAM data instead of zero
rw[204] <= 1'b1; // filter handled configuration TLPs
rw[205] <= 1'b1; // on-board BAR processing
rw[206] <= 1'b1; // permit PCIe writes through the WriteMask
```

`pcileech_tlps128_cfgspace_shadow.sv` decodes `CfgRd0/CfgRd1` and `CfgWr0/CfgWr1`, reads `bram_pcie_cfgspace`, and applies `drom_pcie_cfgspace_writemask` on writes. In that module, `cfgtlp_zero` selects zero versus BRAM read data, and `cfgtlp_wren` gates PCIe-originated writes.

The shadow image and WriteMask have different jobs. `pcileech_cfgspace.coe` supplies the stored DWORDs. `pcileech_cfgspace_writemask.coe` selects which incoming write bits can replace those DWORDs. `pcie_rx_be` carries the TLP byte enables into `bram_wr_be`; a zero byte-enable lane leaves the BRAM lane unchanged. A mask does not implement a register state machine.

The same numeric index can mean something else in another register bank. In `src/pcileech_pcie_cfg_a7.sv`, local `rw[206]` drives `ctx.cfg_interrupt`; it is unrelated to shadow config writes.

## 7. WriteMask

The WriteMask image is `ip/pcileech_cfgspace_writemask.coe`. One mask bit of `1` accepts the corresponding incoming config-write bit; `0` retains the BRAM value:

```systemverilog
assign wr_dina[i] = wr_mask[i] ? wr_data_d[i] : rd_data[i];
```

Generate the mask from an offset/mask CSV. `coe-tools/examples/writemask_structure_test.csv` is a structure test fixture; replace its rows with the donor's actual writable fields:

```powershell
python .\coe-tools\make_writemask_coe.py .\coe-tools\examples\writemask_structure_test.csv .\coe-tools\examples\pcileech_cfgspace_writemask.coe
```

Identity, class, subsystem IDs, DSN, and capability headers normally remain read-only. Command, PMCSR, MSI control/address/data, and PCIe Device Control fields require masks at their actual offsets. A bit mask only chooses old or incoming data; RW1C status behavior requires RTL beyond this mux.

Use these meanings when reviewing a write:

| Type | Check in this tree |
|---|---|
| RO | WriteMask bit is `0`; the old BRAM bit is selected. |
| RW | WriteMask bit is `1`; the byte enable and the owning PCIe core path also have to accept the write. |
| RW1C | The incoming `1` has clear semantics owned by the register implementation; a BRAM mux alone only stores data. |

`src/pcileech_pcie_cfg_a7.sv` owns the core configuration-management path. Its `rw[20]` and `rw[21]` control status auto-clear and command auto-set, while `rw[172:175]` supplies the byte enables for those core writes. Do not use those indices as substitutes for `src/pcileech_fifo.sv` shadow controls.

After replacing the COE, regenerate output products for `drom_pcie_cfgspace_writemask`.

## 8. Capability layout

The standard chain starts at byte `0x34`. Each capability contains an ID and the next pointer. The extended chain starts at `0x100`; its version is in bits `[19:16]` and its next pointer is in bits `[31:20]` of the header.

Do not assume fixed PM, MSI, or PCIe capability offsets. PMCSR is at:

```text
PM capability base + 0x04
```

In the pinned CaptainDMA XCI, MSI is enabled and MSI-X is disabled. The core exports MSI and PM status through `IfPCIeSignals`; `pcileech_pcie_cfg_a7.sv` exposes `ctx.cfg_interrupt_msienable`, `ctx.cfg_pmcsr_powerstate`, `ctx.cfg_pmcsr_pme_en`, and `ctx.cfg_pmcsr_pme_status` in its read-only register bank.

DSN is driven by `rw[127:64]` in `pcileech_pcie_cfg_a7.sv`:

```systemverilog
assign ctx.cfg_dsn = rw[127:64];
```

The same file defines local `rw[20]` as status-register auto-clear enable and local `rw[21]` as command-register auto-set enable. In `pcileech_fifo.sv`, indices `20` and `21` are DRP read and write controls. Always name the module with the index.

For a donor comparison, locate the PM capability through the standard chain and read PMCSR at `PM base + 0x04`. Check `ctx.cfg_pmcsr_powerstate`, `ctx.cfg_pmcsr_pme_en`, and `ctx.cfg_pmcsr_pme_status` in the core register bank. MSI is enabled by the pinned XCI and its state is visible through `ctx.cfg_interrupt_msienable`; MSI-X is disabled and the checked-in RTL has no MSI-X table or PBA implementation. The Command Register path is the core management path, not the shadow BRAM path.

## 9. BAR implementation

`src/pcileech_tlps128_bar_controller.sv` contains the request decoder, read engine, write engine, completion path, and three concrete BAR implementations:

- `pcileech_bar_impl_zerowrite4k`: 4 KB writable BRAM, two-clock read latency;
- `pcileech_bar_impl_loopaddr`: returns the read address, two-clock latency;
- `pcileech_bar_impl_none`: drops accesses and produces no completion.

The checked-in controller connects Zero4K to BAR0 and loopback to BAR1. The XCI enables only BAR0, so the active stock path is Zero4K. Its initial contents come from `ip/pcileech_bar_zero4k.coe` through `bram_bar_zero4k.xci`.

Generate a 1024-DWORD BAR0 image with:

```powershell
python .\coe-tools\make_zero4k_coe.py .\coe-tools\examples\bar0_dwords.csv .\coe-tools\examples\pcileech_bar_zero4k.coe
```

Zero4K covers offsets `0x000` through `0xFFF`. Registers outside that range or state machines with device-specific side effects need corresponding RTL in the BAR controller. Keep every selected BAR implementation at the same read latency, as required by the shared response mux.

The active memory-read path is:

`pcileech_pcie_tlp_a7.sv` `tlps_rx` -> `pcileech_tlps128_bar_controller.sv` request decoder -> `rd_req_valid`, `rd_req_bar`, `rd_req_addr` -> `pcileech_bar_impl_zerowrite4k` -> `rd_rsp_valid`, `rd_rsp_data`, `rd_rsp_ctx` -> BAR response mux -> `pcileech_tlps128_bar_rdengine` -> `tlps_bar_rsp` -> `tlps_tx` Completion.

The controller consumes one DWORD per clock. Reads use `rd_req_addr[11:2]`, so the Zero4K BRAM is DWORD-aligned and read responses carry the full DWORD; the source comments explicitly state that reads have no byte enable. Writes carry `wr_be` and `wr_data`, and Zero4K connects `wr_be` to BRAM `wea`. Zero4K and loopback both return data after two clocks; every implementation selected by the shared mux must preserve that latency.

## 10. Project generation and build

Run each pair of commands from a Vivado Tcl Shell. The generator and build script names below exist in the pinned tree.

CaptainDMA 35T:

```tcl
cd C:/pcileech-fpga/CaptainDMA/35t484_x1
source vivado_generate_project_captaindma_35t.tcl -notrace
source vivado_build.tcl -notrace
puts [get_property STATUS [get_runs synth_1]]
puts [get_property STATUS [get_runs impl_1]]
```

CaptainDMA 75T:

```tcl
cd C:/pcileech-fpga/CaptainDMA/75t484_x1
source vivado_generate_project_captaindma_75t.tcl -notrace
source vivado_build.tcl -notrace
puts [get_property STATUS [get_runs synth_1]]
puts [get_property STATUS [get_runs impl_1]]
```

CaptainDMA 100T:

```tcl
cd C:/pcileech-fpga/CaptainDMA/100t484-1
source vivado_generate_project_captaindma_100t.tcl -notrace
source vivado_build.tcl -notrace
puts [get_property STATUS [get_runs synth_1]]
puts [get_property STATUS [get_runs impl_1]]
```

The generator creates the project below the board directory. `vivado_build.tcl` launches `synth_1`, then `impl_1` through `write_bitstream`, waits for both runs, and copies the generated BIN file back to the board directory.

## 11. Timing review

After `impl_1` completes, keep the project open and create stable report paths:

```tcl
open_run impl_1
file mkdir reports
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 -file reports/timing_summary.rpt
check_timing -verbose -file reports/check_timing.rpt
report_utilization -file reports/utilization.rpt
```

Read WNS and TNS from `reports/timing_summary.rpt`. Review `reports/check_timing.rpt` for unconstrained endpoints, missing clocks, combinational loops, and endpoint coverage. Bitstream generation and timing closure are separate checks; keep the report with the image rather than copying isolated values into the guide.

## 12. BIT and BIN output

| Board | Generated BIT | Copied BIN |
|---|---|---|
| 35T | `pcileech_35t484_x1/pcileech_35t484_x1.runs/impl_1/pcileech_35t484_x1_top.bit` | `pcileech_35t484_x1.bin` |
| 75T | `pcileech_75t484_x1/pcileech_75t484_x1.runs/impl_1/pcileech_75t484_x1_top.bit` | `pcileech_75t484_x1.bin` |
| 100T | `pcileech_100t484_x1/pcileech_100t484_x1.runs/impl_1/pcileech_100t484_x1_top.bit` | `pcileech_100t484_x1.bin` |

The BIT file is the Vivado configuration bitstream. The BIN file is enabled by `steps.write_bitstream.args.bin_file` in each generator and is the image used by the CaptainDMA CH347 flow.

Record hashes directly from the files:

```powershell
Get-FileHash .\pcileech_75t484_x1.bin -Algorithm SHA256
Get-FileHash .\reports\timing_summary.rpt -Algorithm SHA256
```

## 13. Flashing

Use the WCH CH347 FPGA Tool described by the upstream `CaptainDMA/readme.md`:

1. Install the CH347 driver and start the FPGA tool as administrator.
2. Connect the board update port or the matching M2-FW adapter.
3. Confirm the programmer appears before selecting an image.
4. Select the BIN produced for the exact FPGA profile.
5. Program the image and retain the tool output.
6. Remove board power, restore power, and then read the PCIe function again.

Do not substitute a BIN from another CaptainDMA directory. The part, package, constraints, and top module are tied to the selected profile.

## 14. Configuration-space and BAR checks

Start with Device Manager and an offset-aware PCI configuration viewer.

1. Read `0x00`, `0x08`, `0x2C`, `0x34`, and `0x100`.
2. Walk the standard and extended capability pointers.
3. Compare BAR type and aperture size with the donor record.
4. Read BAR0 at `0x000`, another populated DWORD, and `0xFFC`.
5. Write only fields enabled by the WriteMask, then read them back.
6. Re-read the command register and the MSI control field after Windows configures the device.

Enumeration proves that the endpoint trained and answered configuration requests. BAR completion proves that the selected MMIO path responds. Driver operation adds device-specific behavior beyond both checks.

## 14.1 ILA probes

The checked-in project has no ILA instance. When adding one to a generated project, keep probes at the existing module boundaries and trigger on the transaction under review.

| Check | Probes from the source |
|---|---|
| Config write | `pcie_rx_wren`, `pcie_rx_addr`, `pcie_rx_data`, `pcie_rx_be`, `bram_wr_be`, `bram_rd_data_z`, `tlps_cfg_rsp.tvalid` |
| BAR read | `tlps_in.tvalid`, `tlps_in.tlast`, `tlps_in.tdata`, `in_is_bar`, `rd_req_valid`, `rd_req_bar`, `rd_req_addr`, `rd_rsp_valid`, `rd_rsp_data`, `bar_rsp_valid[0]` |
| Interrupt | `ctx.cfg_interrupt`, `ctx.cfg_interrupt_assert`, `ctx.cfg_interrupt_rdy`, `ctx.cfg_interrupt_msienable`, `ctx.cfg_interrupt_msixenable` |

For a config write, trigger on `pcie_rx_wren` and compare `pcie_rx_be` with the WriteMask result. For a BAR read, trigger on `rd_req_valid` and require a matching `rd_rsp_valid` after the implementation latency. For MSI, trigger on `ctx.cfg_interrupt` and inspect the ready and enable signals together.

## 15. Common problems

| Symptom | Check | Action |
|---|---|---|
| Vivado reports the wrong part | Project part and selected board directory | Regenerate from the matching CaptainDMA Tcl file |
| Config reads after the header return zero | `rw[203]` in `pcileech_fifo.sv` | Set it to `0` and regenerate the BRAM output products |
| Config writes do not change shadow data | `rw[206]` in `pcileech_fifo.sv` and the WriteMask | Enable the shadow write path and set only required mask bits |
| BAR0 read has no completion | `bar_en`, BAR0 XCI setting, and `i_bar0` | Keep BAR0 enabled and trace `rd_req_valid` to `rd_rsp_valid` |
| POST stops before Windows | Board part, XDC, stock image, and selected BIN | Restore the exact board profile and check the programmer connection |
| Device Manager shows Code 10 or Code 43 | Config chain, BAR0 readback, Command, MSI, PMCSR, and the first driver MMIO access | Fix the first divergent layer; the checked-in Zero4K path has no device-specific state machine |
| A config write changes the wrong bytes | TLP byte enable, WriteMask DWORD, and `bram_wr_be` | Check the actual capability offset and the four byte lanes before changing the mask |
| BAR read returns data but no Completion reaches the core | `rd_rsp_valid`, `rd_rsp_ctx`, response mux, and `tlps_bar_rsp` | Preserve the two-clock implementation latency and trace the response FIFO |
| MSI request never appears | `ctx.cfg_interrupt_msienable`, `ctx.cfg_interrupt_rdy`, and `ctx.cfg_interrupt` | Check the donor MSI capability and the core interrupt handshake |
| PMCSR or Command readback differs | Capability base, `rw[20]`, `rw[21]`, `ctx.cfg_mgmt_*`, and byte enables | Keep core-managed fields in the core management path; do not mask a fixed offset |
| Host blue-screens during config or BAR access | WriteMask, RW1C handling, byte enables, out-of-range BAR accesses, and timing reports | Stop at the first malformed response or timing violation and restore the last known image |
| BAR0 returns stale initialization data | `pcileech_bar_zero4k.coe` and `bram_bar_zero4k` | Replace the board-local COE and regenerate that IP |
| Build output uses an unexpected name | Project directory and `file copy` line in `vivado_build.tcl` | Use the project name created by the selected generator |
| Timing report lists unconstrained endpoints | `check_timing.rpt` and XDC clock definitions | Fix the clock or path constraint before using the image |
| CH347 opens but the board identity is wrong | Board marking, adapter orientation, and selected BIN | Return to the exact board profile and stock image |

## 16. Linux supplement

Linux is useful for an offset-preserving 4096-byte donor capture. Set the BDF and output directory, then run:

```bash
set -euo pipefail

BDF="0000:03:00.0"
OUT="donor-capture"
mkdir -p "$OUT"

if command -v mokutil >/dev/null 2>&1; then
    mokutil --sb-state | tee "$OUT/secure-boot-state.txt"
else
    echo "mokutil not installed; Secure Boot state unavailable" |
        tee "$OUT/secure-boot-state.txt"
fi

lspci -s "$BDF" -nn > "$OUT/lspci-nn.txt"
lspci -s "$BDF" -vvv > "$OUT/lspci-vvv.txt"
lspci -s "$BDF" -xxxxxxx > "$OUT/config-4096.txt"
cat "/sys/bus/pci/devices/$BDF/resource" > "$OUT/resource.txt"
sudo dd if="/sys/bus/pci/devices/$BDF/config" \
    of="$OUT/config-4096.bin" bs=4096 count=1 status=progress
stat -c '%s %n' "$OUT/config-4096.bin"
sha256sum "$OUT"/* > "$OUT/SHA256SUMS"
```

The binary must retain byte offsets. `resource.txt` supplies assigned resource ranges and aperture sizes; the config BAR DWORD by itself does not supply the aperture size.

## 17. File and term reference

| Purpose | File or module |
|---|---|
| PCIe hard-IP settings | `ip/pcie_7x_0.xci` |
| Shadow config data | `ip/pcileech_cfgspace.coe` |
| Shadow write mask | `ip/pcileech_cfgspace_writemask.coe` |
| Shadow controls | `src/pcileech_fifo.sv` |
| Config TLP decode and BRAM mux | `src/pcileech_tlps128_cfgspace_shadow.sv` |
| DSN, config-management controls, interrupt pins | `src/pcileech_pcie_cfg_a7.sv` |
| BAR request, response, and implementations | `src/pcileech_tlps128_bar_controller.sv` |
| Zero4K contents | `ip/pcileech_bar_zero4k.coe` |
| Board pins and clocks | board-specific `.xdc` under `src/` |
| Project creation | board-specific `vivado_generate_project_*.tcl` |
| Synthesis and implementation | `vivado_build.tcl` |
