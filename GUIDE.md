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

## 9. BAR implementation and device engine

The existing BAR path is worth keeping. In `src/pcileech_tlps128_bar_controller.sv`, `pcileech_tlps128_bar_wrengine` already decodes Memory Write requests into `wr_bar`, `wr_addr`, `wr_be`, `wr_data`, and `wr_valid`. `pcileech_tlps128_bar_rdengine` turns a host Memory Read into DWORD requests, preserves Requester ID and Tag in `rd_req_ctx`, and returns one or more CplD packets through `tlps_bar_rsp`.

The stock BAR0 implementation, `pcileech_bar_impl_zerowrite4k`, is only a 4 KB byte-enabled RAM. Use it to prove MMIO transport first. Replace it when the driver starts expecting registers, commands, queue state, DMA, or interrupts.

For that baseline, [`make_zero4k_coe.py`](coe-tools/make_zero4k_coe.py) builds the image from the [BAR0 DWORD CSV](coe-tools/examples/bar0_dwords.csv). Keep the known Zero4K image available while changing the register block; it separates BAR transport faults from device-state faults.

Work in this order:

1. replace Zero4K with a dynamic BAR register block while preserving the two-clock read response;
2. reproduce the driver's command/status transitions;
3. add one outbound TLP source to the existing TX arbiter;
4. add a Tag table and consume only the Completions owned by that table;
5. fetch and retire descriptors;
6. connect the event path to the existing MSI owner;
7. reset the whole device engine on FLR, Hot Reset, and subsystem reset;
8. run simulation before adding the driver.

The [RTL ownership notes](firmware-notes/implementation-notes.md) list the existing modules and clock crossings used below.

| File | Change made by this chapter |
|---|---|
| `src/pcileech_tlps128_bar_controller.sv` | Replace `i_bar0`; add dynamic registers, side effects, queue state, and the device scheduler |
| `src/pcileech_pcie_tlp_a7.sv` | Add the DMA TX stream, Completion ownership, and the fifth TX-mux input |
| `src/pcileech_pcie_a7.sv` | Route live Command, Device Control, PM, link, FLR, Hot Reset, and interrupt-event signals |
| `src/pcileech_pcie_cfg_a7.sv` | Keep one owner for MSI, transaction-pending, and turnoff acknowledgement |
| `src/pcileech_header.svh` | Extend an interface only if the added signals are not kept as explicit module ports |

### 9.1 Replace Zero4K with a dynamic BAR block

Keep the decoder and both BAR engines. In `src/pcileech_tlps128_bar_controller.sv`, replace only the module attached to `i_bar0`. The replacement uses the same ports:

```systemverilog
module pcileech_bar_impl_device(
    input               rst,
    input               clk,

    input      [31:0]   wr_addr,
    input      [3:0]    wr_be,
    input      [31:0]   wr_data,
    input               wr_valid,

    input      [87:0]   rd_req_ctx,
    input      [31:0]   rd_req_addr,
    input               rd_req_valid,

    output bit [87:0]   rd_rsp_ctx,
    output bit [31:0]   rd_rsp_data,
    output bit          rd_rsp_valid,

    output bit          command_pulse,
    output bit          queue_enable,
    output bit [63:0]   queue_base,
    output bit [15:0]   queue_size,
    output bit [15:0]   producer_index,

    input      [15:0]   consumer_index,
    input      [31:0]   engine_status,
    input               engine_done,
    input               engine_error
);
```

Use symbolic offsets until the driver's BAR trace identifies the real addresses:

```systemverilog
localparam [11:0] REG_CONTROL      = 12'h000;
localparam [11:0] REG_STATUS       = 12'h004;
localparam [11:0] REG_QUEUE_BASE_LO= 12'h008;
localparam [11:0] REG_QUEUE_BASE_HI= 12'h00c;
localparam [11:0] REG_QUEUE_SIZE   = 12'h010;
localparam [11:0] REG_PRODUCER     = 12'h014;
localparam [11:0] REG_CONSUMER     = 12'h018;
localparam [11:0] REG_DOORBELL     = 12'h01c;
```

Those values are a wiring example, not donor data. Replace each one with the offset read or written by the driver. Do the same for reset values and field definitions.

The write engine already converts an unaligned host access into a DWORD address and byte enables. Merge only enabled lanes:

```systemverilog
function automatic [31:0] apply_be(
    input [31:0] old_value,
    input [31:0] new_value,
    input [3:0]  be
);
    integer lane;
    begin
        apply_be = old_value;
        for (lane = 0; lane < 4; lane = lane + 1)
            if (be[lane])
                apply_be[lane*8 +: 8] = new_value[lane*8 +: 8];
    end
endfunction

bit [31:0] control_reg;
bit [31:0] status_reg;

wire [31:0] write_lane_mask = {
    {8{wr_be[3]}}, {8{wr_be[2]}}, {8{wr_be[1]}}, {8{wr_be[0]}}
};
```

A register write and its side effect must be handled by the same address hit. This avoids a doorbell firing when its byte lane was not written:

```systemverilog
wire control_wr  = wr_valid && (wr_addr[11:0] == REG_CONTROL);
wire status_wr   = wr_valid && (wr_addr[11:0] == REG_STATUS);
wire doorbell_wr = wr_valid && (wr_addr[11:0] == REG_DOORBELL);

always @(posedge clk) begin
    if (rst) begin
        queue_enable  <= 1'b0;
        command_pulse <= 1'b0;
    end else begin
        command_pulse <= 1'b0;

        if (control_wr) begin
            control_reg <= apply_be(control_reg, wr_data, wr_be);
            queue_enable <= wr_be[0] ? wr_data[0] : queue_enable;
        end

        if (doorbell_wr && wr_be[0] && wr_data[0])
            command_pulse <= 1'b1;
    end
end
```

Do not implement W1C by storing the written value. Set status from hardware events, then clear only the enabled bits written as one:

```systemverilog
wire [31:0] status_set = {
    30'b0, engine_error, engine_done
};

always @(posedge clk) begin
    if (rst)
        status_reg <= 32'h00000000;
    else if (status_wr)
        status_reg <= (status_reg &
                      ~(wr_data & write_lane_mask)) |
                      status_set;
    else
        status_reg <= status_reg | status_set;
end
```

This ordering gives a hardware event priority over a simultaneous W1C acknowledgement, so a new event is not lost.

The shared BAR read engine expects the implementation response after two clocks. Pipeline the address and context together:

```systemverilog
bit [87:0] rd_ctx_q;
bit [11:0] rd_addr_q;
bit        rd_valid_q;

always @(posedge clk) begin
    rd_ctx_q   <= rd_req_ctx;
    rd_addr_q  <= rd_req_addr[11:0];
    rd_valid_q <= rd_req_valid;

    rd_rsp_ctx   <= rd_ctx_q;
    rd_rsp_valid <= rd_valid_q;

    case (rd_addr_q)
        REG_CONTROL:       rd_rsp_data <= control_reg;
        REG_STATUS:        rd_rsp_data <= status_reg | engine_status;
        REG_QUEUE_BASE_LO: rd_rsp_data <= queue_base[31:0];
        REG_QUEUE_BASE_HI: rd_rsp_data <= queue_base[63:32];
        REG_QUEUE_SIZE:    rd_rsp_data <= {16'b0, queue_size};
        REG_PRODUCER:      rd_rsp_data <= {16'b0, producer_index};
        REG_CONSUMER:      rd_rsp_data <= {16'b0, consumer_index};
        default:           rd_rsp_data <= 32'h00000000;
    endcase
end
```

If the donor uses read-clear, snapshot, or latch-on-read registers, apply that action when `rd_req_valid` and the matching address are accepted. Do not trigger it from `rd_rsp_valid`, because the response can be delayed while a later request is already entering the pipeline.

### 9.2 Add the device command/status state machine

The command state machine in `src/pcileech_fifo.sv` belongs to the FT601 control protocol. Leave it alone. Put driver-visible device state next to the BAR registers or in a new module appended to `src/pcileech_tlps128_bar_controller.sv`, all in `clk_pcie`.

Route these existing core signals from `pcileech_pcie_a7.sv` through `pcileech_pcie_tlp_a7.sv`:

```systemverilog
input  [15:0] cfg_command;
input  [15:0] cfg_dcommand;
input  [15:0] cfg_dcommand2;
input   [1:0] pm_power_state;
input         link_up;
input         flr;
input         hot_reset;
output        device_irq_req;
```

At the wrapper level, keep `ctx` as the source of core state and use one wire for the engine event:

```systemverilog
wire device_irq_req;

pcileech_pcie_cfg_a7 i_pcileech_pcie_cfg_a7(
    // existing ports...
    .device_irq_req ( device_irq_req )
);

pcileech_pcie_tlp_a7 i_pcileech_pcie_tlp_a7(
    // existing ports...
    .cfg_command     ( ctx.cfg_command                 ),
    .cfg_dcommand    ( ctx.cfg_dcommand                ),
    .cfg_dcommand2   ( ctx.cfg_dcommand2               ),
    .pm_power_state  ( ctx.cfg_pmcsr_powerstate        ),
    .link_up         ( ctx.pl_phy_lnk_up               ),
    .flr             ( ctx.cfg_received_func_lvl_rst   ),
    .hot_reset       ( ctx.pl_received_hot_rst         ),
    .device_irq_req  ( device_irq_req                  )
);
```

Use `ctx.cfg_command[1]` for Memory Space Enable and `ctx.cfg_command[2]` for Bus Master Enable. Do not copy those values from the shadow BRAM. The Xilinx core owns the live Command Register and already exposes it as `ctx.cfg_command`.

A small state machine is enough to control request issue:

```systemverilog
typedef enum logic [2:0] {
    DEV_RESET,
    DEV_IDLE,
    DEV_READY,
    DEV_FETCH_DESC,
    DEV_RUN,
    DEV_COMPLETE,
    DEV_FAULT
} device_state_t;

wire mmio_enabled = cfg_command[1];
wire bus_master   = cfg_command[2];
wire power_d0     = (pm_power_state == 2'b00);
wire can_run      = link_up && power_d0 && bus_master;

always @(posedge clk_pcie) begin
    if (engine_reset) begin
        state <= DEV_RESET;
    end else case (state)
        DEV_RESET:
            state <= DEV_IDLE;

        DEV_IDLE:
            if (mmio_enabled && queue_config_valid)
                state <= DEV_READY;

        DEV_READY:
            if (command_pulse && queue_enable && can_run)
                state <= DEV_FETCH_DESC;

        DEV_FETCH_DESC:
            if (descriptor_ready)
                state <= DEV_RUN;
            else if (request_error)
                state <= DEV_FAULT;

        DEV_RUN:
            if (transfer_done)
                state <= DEV_COMPLETE;
            else if (request_error)
                state <= DEV_FAULT;

        DEV_COMPLETE:
            if (completion_recorded)
                state <= DEV_READY;

        DEV_FAULT:
            if (status_w1c_ack)
                state <= DEV_READY;
    endcase
end
```

`queue_config_valid`, ready, busy, done, and error must match the actual driver-visible fields. Capture the first driver load and write down the order before assigning those bits. The important behavior is the transition: configuration writes first, enable or doorbell next, busy while requests are live, status or consumer update at retirement, then interrupt.

### 9.3 Add Memory Read and Memory Write generation

The pinned tree can transmit arbitrary TLP DWORDs from `dfifo.tx_*` and can send the eight-DWORD static packet in `pcileech_pcie_cfg_a7.sv`. Neither path schedules descriptors or owns Tags.

Add an `IfAXIS128 tlps_dma()` stream in `src/pcileech_pcie_tlp_a7.sv`. Extend `pcileech_tlps128_sink_mux1` from four inputs to five. Preserve the current first three priorities and insert DMA before the static source:

```text
1  tlps_cfg_rsp
2  tlps_bar_rsp
3  tlps_rx_fifo
4  tlps_dma
5  tlps_static
```

The mux already holds a selected source until `tvalid && tlast`. Add `tlps_in5` to the port list, `has_data` expression, data selectors, `id_next_newsel`, and `tready` assignments. Do not connect a second driver directly to `tlps_tx`.

The request generator needs these inputs:

```systemverilog
input      [15:0] requester_id;
input      [15:0] cfg_dcommand;
input      [63:0] request_addr;
input      [31:0] request_length;
input             request_is_write;
input      [127:0] write_data;
input      [15:0] write_keep;
input             request_valid;
output            request_ready;
IfAXIS128.source  tlps_dma;
```

Decode the active limits from the real Device Control register:

- `cfg_dcommand[7:5]`: Maximum Payload Size for Memory Write;
- `cfg_dcommand[14:12]`: Maximum Read Request Size;
- `cfg_dcommand[8]`: Extended Tag Field Enable.

The byte limits decode as `128 << field_value`; clamp them to the limits configured into the generated core and to the buffer size implemented by the engine.

Start with Tags 0 through 31. Use a larger pool only when Extended Tag is enabled and the generated core configuration supports it.

For each fragment:

```text
bytes_to_4k = 4096 - request_addr[11:0]
limit       = request_is_write ? max_payload_bytes : max_read_request_bytes
fragment    = min(remaining_bytes, bytes_to_4k, limit)
```

The request must not cross a 4 KB boundary. Compute Length in DWORDs after accounting for the first and last partial DWORD. First Byte Enable comes from the start address and leading byte count; Last Byte Enable comes from the final DWORD. A one-DWORD request uses First Byte Enable and a zero Last Byte Enable.

```systemverilog
wire [1:0] start_lane = fragment_addr[1:0];
wire [1:0] end_lane   =
    (fragment_addr[1:0] + fragment_bytes - 1) & 2'b11;
wire [10:0] fragment_dw =
    (fragment_addr[1:0] + fragment_bytes + 3) >> 2;
wire [9:0] length_field = (fragment_dw == 1024) ?
                          10'b0000000000 : fragment_dw[9:0];

wire [3:0] first_be_raw = 4'b1111 << start_lane;
wire [3:0] last_be_raw  = 4'b1111 >> (3 - end_lane);
wire [3:0] first_be = (fragment_dw == 1) ?
                      (first_be_raw & last_be_raw) : first_be_raw;
wire [3:0] last_be  = (fragment_dw == 1) ?
                      4'b0000 : last_be_raw;
```

Reject a zero-length transfer before this calculation. PCIe encodes a Length field of zero as 1024 DWORDs, not as an empty request.

Build the header in the same DWORD order used by `pcileech_tlps128_bar_rdengine` and `pcileech_cfgspace_pcie_tx`:

| Header DWORD | Memory request fields |
|---|---|
| DW0 | Fmt, Type, traffic attributes, and Length |
| DW1 | Requester ID, Tag, Last BE, First BE |
| DW2 | 32-bit address, or upper 32 bits of a 64-bit address |
| DW3 | lower 32 bits for a 4-DWORD header; otherwise the first payload DWORD |

Use a 3-DWORD Memory Read/Write header below 4 GB and a 4-DWORD header above it. A Memory Write is posted: retire its TX fragment when the final beat is accepted by `tlps_dma.tready`. A Memory Read is non-posted: move it to the outstanding table after the header is accepted, then wait for Cpl/CplD.

A practical TX state machine is:

```text
TX_IDLE
  -> TX_ALLOC_TAG       Memory Read only
  -> TX_HEADER
  -> TX_PAYLOAD         Memory Write only
  -> TX_FRAGMENT_DONE
  -> TX_IDLE            no bytes left
  -> TX_HEADER          next split fragment
```

Keep `tdata`, `tkeepdw`, `tlast`, and `tvalid` unchanged whenever `tvalid == 1` and `tready == 0`. Set `tuser[0]` on the first beat and `tuser[1]` with the last beat. The static source and BAR response code show the byte order expected by the existing 128-to-64 converter; compare the complete transmitted header in simulation before hardware use.

### 9.4 Consume Completions and manage Tags

`pcileech_tlps128_filter` already identifies Cpl and CplD with `tlps_in.tdata[31:25]`. It forwards them unchanged through `pcileech_tlps128_dst_fifo`; it does not parse status, own Tags, reassemble data, or time out requests.

On the first beat of a Completion, the fields used by the request engine are:

| Field | Existing 128-bit stream |
|---|---|
| Cpl/CplD type | `tlps_rx.tdata[31:25]` |
| Length | `tlps_rx.tdata[9:0]` |
| Completion Status | `tlps_rx.tdata[47:45]` |
| Byte Count | `tlps_rx.tdata[43:32]` |
| Requester ID | `tlps_rx.tdata[95:80]` |
| Tag | `tlps_rx.tdata[79:72]` |
| Lower Address | `tlps_rx.tdata[70:64]` |
| First payload DWORD | `tlps_rx.tdata[127:96]` for CplD |

Create a live table in `clk_pcie`. One entry per issued Memory Read is sufficient:

```systemverilog
typedef struct packed {
    logic        valid;
    logic [63:0] request_addr;
    logic [31:0] total_bytes;
    logic [31:0] received_bytes;
    logic [15:0] descriptor_index;
    logic [31:0] age;
} tag_entry_t;

tag_entry_t tag_table [0:31];
logic [31:0] tag_free;
wire  [31:0] tag_live = ~tag_free;
```

Allocation clears one bit in `tag_free` and writes the matching entry. Do not free the Tag when the first CplD arrives. Free it after `received_bytes == total_bytes`, or once after a non-success Completion or timeout has been committed to the descriptor error path.

For each owned CplD:

1. reject a Tag whose `valid` bit is clear;
2. check Completion Status before accepting payload;
3. verify Byte Count does not exceed the bytes still expected;
4. use Lower Address to place the first payload byte;
5. apply `tkeepdw` on every beat and append only valid payload DWORDs;
6. increase `received_bytes` by accepted payload bytes;
7. retire the request only after the complete byte count has arrived.

Different Tags can complete out of order. Several CplD packets can complete one request. Keep descriptor completion separate from packet completion.

Add a Tag-age counter or a shared timer scan. At timeout, mark the owning descriptor with an error and remove the request from normal completion accounting. Do not immediately reuse that Tag: a late Completion carries only the Tag, not a private generation number. Keep timed-out Tags in a quarantine bitmap until FLR/reset or until a guard interval longer than the accepted completion window has expired, and drop late packets that match the quarantine bitmap.

Owned Completion packets should not also appear as ordinary FT601 RX traffic. Add an ownership input to `pcileech_tlps128_filter` and include it in `filter_next` for the whole packet. Ownership is true only when the first beat is Cpl/CplD and `tag_table[tag].valid` belongs to the device engine. Requests injected through `dfifo.tx_*` share the same PCIe Tag namespace; reserve disjoint Tag ranges or serialize those requests with the device engine.

The 2-bit `p0_tag` through `p7_tag` values in `src/pcileech_mux.sv` are FT601 channel labels. They have no relationship to the 8-bit PCIe Tag.

### 9.5 Fetch descriptors and run the queue

The existing Xilinx FIFOs transport TLP beats and control words. They are not driver-visible descriptor queues.

Use the BAR block for queue configuration:

- queue base low and high;
- ring size;
- producer index written by the driver;
- consumer index written by the engine;
- enable;
- doorbell;
- interrupt mask or moderation fields when present in the driver ABI.

Keep the register offsets, descriptor size, and field layout identical to the driver. A typical engine sequence is:

```text
driver writes queue base and size
driver writes producer index
driver rings doorbell
engine validates base, size, producer, and Bus Master Enable
engine issues MRd for descriptor[consumer]
Completion parser assembles the descriptor
engine validates address, length, direction, and flags
engine performs data MRd/MWr fragments
engine writes descriptor status if the ABI requires it
engine advances consumer
engine sets completion status and interrupt pending
```

Do not advance `consumer_index` when the descriptor is fetched. Advance it after every request owned by that descriptor has reached completion or a terminal error. For a ring of `queue_size` entries:

```systemverilog
wire queue_empty = (consumer_index == producer_index);
wire [15:0] next_consumer =
    (consumer_index + 1 == queue_size) ? 16'd0 : consumer_index + 1;
```

Reject a zero size, a producer outside the ring, an address alignment the descriptor format does not allow, and a transfer length larger than the implemented counter or buffer. Split descriptor fetches and data requests independently; a descriptor that crosses a 4 KB boundary still needs two Memory Reads.

Keep the queue scheduler, Tag table, and TX source in `clk_pcie`. If payload data must move to `clk_sys`, cross a complete record through an asynchronous FIFO. Follow `fifo_134_134_clk2_rxfifo` for system-to-PCIe traffic and `fifo_134_134_clk2` for PCIe-to-system traffic. Do not cross a producer pointer, descriptor, or one-clock pulse by sampling it directly in the other domain.

### 9.6 Connect MSI, then add MSI-X only if required

The checked-in `ip/pcie_7x_0.xci` enables one 64-bit MSI vector and disables MSI-X. In `src/pcileech_pcie_cfg_a7.sv`, local `rw[206]` currently drives `ctx.cfg_interrupt`.

Add one `device_irq_req` input to `pcileech_pcie_cfg_a7`. Replace the direct level assignment with a pending latch owned by this module:

```systemverilog
bit device_irq_pending;
wire irq_ack = ctx.cfg_interrupt &&
               ctx.cfg_interrupt_rdy;

always @(posedge clk_pcie) begin
    if (rst)
        device_irq_pending <= 1'b0;
    else case ({device_irq_req, irq_ack})
        2'b10, 2'b11: device_irq_pending <= 1'b1;
        2'b01:        device_irq_pending <= 1'b0;
        default:      device_irq_pending <= device_irq_pending;
    endcase
end

assign ctx.cfg_interrupt =
    (device_irq_pending || rw[206]) &&
    ctx.cfg_interrupt_msienable;
```

If `rw[206]` remains as a diagnostic request, self-clear it on `irq_ack`; otherwise a level left high can request another interrupt. Keep the pending status visible through the BAR register used by the driver. Masking an event stops transmission but does not discard the pending bit.

For MSI-X, first enable it in the XCI and regenerate the PCIe IP. Then implement the table and Pending Bit Array at the BIR and offsets declared by the capability. Each vector needs address, data, and vector-control mask fields. Function mask and vector mask both suppress transmission; a suppressed event sets the matching PBA bit. When the vector is unmasked, issue it and clear the PBA bit only after the core accepts the interrupt. The stock Zero4K BAR is not an MSI-X table implementation.

### 9.7 Reset, FLR, link recovery, and power

`src/pcileech_pcie_a7.sv` currently defines:

```systemverilog
wire rst_subsys = rst || rst_pcie_user ||
                  dfifo_pcie.pcie_rst_subsys;
wire rst_pcie   = rst || ~pcie_perst_n ||
                  dfifo_pcie.pcie_rst_core;
```

The core also exposes `ctx.cfg_received_func_lvl_rst`, `ctx.pl_received_hot_rst`, `ctx.pl_phy_lnk_up`, `ctx.pl_ltssm_state`, `ctx.cfg_pcie_link_state`, and `ctx.cfg_pmcsr_powerstate`.

Form a synchronous device-engine reset in `clk_pcie`:

```systemverilog
wire engine_reset =
    rst_subsys ||
    ctx.cfg_received_func_lvl_rst ||
    ctx.pl_received_hot_rst;
```

On `engine_reset`:

- clear the Tag live map and timeout state;
- discard partial Completion and descriptor assembly;
- clear queue enable, consumer ownership, and doorbell pulses;
- drop pending device interrupts;
- restore dynamic BAR reset values;
- return TX and device state machines to idle.

Link loss is not a reason to keep issuing. Stop new requests as soon as `ctx.pl_phy_lnk_up` drops. Clear transport state that cannot survive retraining, then wait for link-up and the driver's queue programming before accepting another doorbell. The `STARTUPE2` global reset in `pcileech_fifo.sv` reloads the FPGA and is not FLR handling.

`ctx.cfg_pmcsr_powerstate == 2'b00` is D0. Outside D0, stop fetching descriptors and requesting interrupts. Decide from the driver/device behavior whether in-flight work drains or aborts before D3. Drive `ctx.cfg_trn_pending` while transactions are still owned and assert `ctx.cfg_turnoff_ok` only when the engine is ready for the requested power transition. The existing `rw[208:214]` controls expose the core PM pins; they do not provide this device state machine.

### 9.8 Reproduce the driver initialization handshake

The `initial_rx` word in `src/pcileech_com.sv` releases the PCILeech transport from startup reset. It is separate from a Windows driver's device initialization.

Capture the first successful driver start and annotate every BAR access in order:

1. Command Register reaches the required Memory Space and Bus Master state.
2. The driver maps BAR0 and reads identity, version, or capability registers.
3. Queue base and size registers are written.
4. Producer and consumer state is initialized.
5. MSI or MSI-X is configured and unmasked.
6. The driver writes enable or rings the first doorbell.
7. The device sets busy or clears ready.
8. Descriptor fetch and payload DMA complete.
9. The device updates status or consumer state.
10. The interrupt is acknowledged and status is cleared.

Implement the same dependencies. Do not assert ready immediately after enumeration. Reject a doorbell until every required queue field is valid, Bus Master Enable is set, the link is up, and the function is in D0. If the driver polls before enabling interrupts, update status before requesting MSI. If it acknowledges with W1C, keep the event set until that exact write is received.

Use ILA in two passes. First capture `wr_valid`, `wr_addr`, `wr_be`, `wr_data`, state, and BAR readback to finish the register handshake. Then capture the DMA TX header, live Tag, CplD header, received byte count, consumer update, `device_irq_pending`, `ctx.cfg_interrupt`, and `ctx.cfg_interrupt_rdy`. Driver load is complete only when this whole chain reaches the expected final state.

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

### 10.1 RTL simulation before build

The CaptainDMA profiles at the pinned revision do not include a device-engine testbench. Add the testbench to the Vivado simulation set in the same working tree as the RTL under test; do not treat the synthesis run as protocol verification.

Start with the BAR block by itself. Drive `wr_*` and `rd_req_*` directly, keep a two-entry queue of expected `rd_req_ctx` values, and compare each one when `rd_rsp_valid` arrives. Then place the request engine behind an `IfAXIS128` sink that can deassert `tready` for arbitrary intervals. The Completion driver sends complete 128-bit beats with the same `tuser[0]`, `tlast`, and `tkeepdw` convention used by `pcileech_tlps128_dst_fifo`.

Run the transaction sequence in a fixed order:

1. hold reset across several `clk_pcie` edges and check that queue, Tag, TX, interrupt, and status state is empty;
2. write every BAR register once with `wr_be` values `0001`, `0010`, `0100`, `1000`, and `1111`, then read it back through the two-clock path;
3. write the doorbell with its byte disabled and confirm that no command pulse appears;
4. ring the doorbell with Bus Master Enable clear and confirm that the TX source remains idle;
5. enable bus mastering, issue one MRd, capture its Tag, and return one CplD with matching Requester ID, Tag, Byte Count, and Lower Address;
6. issue several MRds and return their CplD packets in a different Tag order, splitting at least one request across two packets;
7. withhold a Completion until timeout, send it late, and confirm that the quarantined Tag is not attached to a later request;
8. hold `tready` low in the middle of a header and payload and compare every output signal for stability;
9. complete a descriptor, delay `cfg_interrupt_rdy`, and confirm that the pending event survives until acknowledgement;
10. assert FLR and Hot Reset while requests are live and check that no old Tag, descriptor, packet beat, or interrupt remains afterward.

Useful assertions at the module boundary are:

```systemverilog
assert property (@(posedge clk_pcie)
    tlps_dma.tvalid && !tlps_dma.tready |=>
    tlps_dma.tvalid && $stable({tlps_dma.tdata,
                               tlps_dma.tkeepdw,
                               tlps_dma.tlast,
                               tlps_dma.tuser}));

assert property (@(posedge clk_pcie)
    tag_allocate |-> tag_free[tag_allocate_value]);

assert property (@(posedge clk_pcie)
    engine_reset |=> !(|tag_live) &&
                      !device_irq_pending &&
                      !tlps_dma.tvalid);
```

Use a scoreboard for BAR latency and Completion byte placement. It should compare the full `rd_req_ctx`, request address, Tag, expected destination offset, accepted payload bytes, and final descriptor result rather than checking only a done flag.

Exercise these cases before implementation:

| Area | Required stimulus and check |
|---|---|
| BAR registers | Full and partial byte enables, unaligned host writes as decoded by the write engine, W1C status, doorbell pulse width, read side effects, and the two-clock `rd_req_valid` to `rd_rsp_valid` pipeline |
| Memory Write | 32-bit and 64-bit addresses, first/last byte enables, maximum payload split, 4 KB boundary split, and `tvalid` stability under TX backpressure |
| Memory Read | Multiple live Tags, exhausted Tag pool, read-request split, and no issue while Bus Master Enable is clear |
| Completion | CplD split into several packets, different Tags returned out of order, non-success status, duplicate data, wrong Byte Count, and timeout release |
| Queue | Producer/consumer wrap, invalid descriptor length, doorbell while disabled, descriptor completion ordering, and backpressure at every FIFO boundary |
| Interrupt | MSI disabled, delayed `cfg_interrupt_rdy`, coalesced pending events, and no lost event during acknowledgement |
| Reset and power | FLR, Hot Reset, link loss during a request, D3 entry with work pending, return to D0, and reinitialization before a new doorbell |

For the TLP checks, compare complete headers and payload bytes, not only `tvalid`. Assert that a Tag is never issued twice, every accepted MRd reaches completion or timeout exactly once, and reset leaves no request or interrupt pending.

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
7. Compare the driver's first BAR writes with the implemented command/status transition.
8. Check one DMA read and one DMA write with byte-for-byte comparison in a driver-owned buffer.
9. Verify Tag retirement, timeout behavior, queue movement, and interrupt acknowledgement separately.
10. Repeat the initialization after FLR or the reset sequence supported by the driver.

Enumeration proves that the endpoint trained and answered configuration requests. BAR completion proves that the selected MMIO path responds. Driver operation adds device-specific behavior beyond both checks.

## 14.1 ILA probes

The checked-in project has no ILA instance. When adding one to a generated project, keep probes at the existing module boundaries and trigger on the transaction under review.

| Check | Probes from the source |
|---|---|
| Config write | `pcie_rx_wren`, `pcie_rx_addr`, `pcie_rx_data`, `pcie_rx_be`, `bram_wr_be`, `bram_rd_data_z`, `tlps_cfg_rsp.tvalid` |
| BAR read | `tlps_in.tvalid`, `tlps_in.tlast`, `tlps_in.tdata`, `in_is_bar`, `rd_req_valid`, `rd_req_bar`, `rd_req_addr`, `rd_rsp_valid`, `rd_rsp_data`, `bar_rsp_valid[0]` |
| Interrupt | `ctx.cfg_interrupt`, `ctx.cfg_interrupt_assert`, `ctx.cfg_interrupt_rdy`, `ctx.cfg_interrupt_msienable`, `ctx.cfg_interrupt_msixenable` |
| Raw Completion receive | `is_tlphdr_cpl`, `tlps_filtered.tvalid`, `tlps_filtered.tdata`, `dfifo.rx_valid`, `dfifo.rx_data` |
| Reset and link | `rst_subsys`, `rst_pcie_user`, `ctx.cfg_received_func_lvl_rst`, `ctx.pl_received_hot_rst`, `ctx.pl_phy_lnk_up`, `ctx.pl_ltssm_state` |

For a config write, trigger on `pcie_rx_wren` and compare `pcie_rx_be` with the WriteMask result. For a BAR read, trigger on `rd_req_valid` and require a matching `rd_rsp_valid` after the implementation latency. For MSI, trigger on `ctx.cfg_interrupt` and inspect the ready and enable signals together.

### 14.2 Hardware regression

Run the [hardware regression record](firmware-notes/templates.md#hardware-regression-record) from a cold power cycle. Keep the configuration and BAR captures from the same boot.

1. Confirm link training and enumerate the function before loading the driver.
2. Walk both capability chains, then compare Command, PMCSR, MSI control, BAR type, and BAR aperture with the captured device state.
3. Load the driver and record the initial BAR transaction order. The ready transition must follow the required queue and interrupt programming.
4. Read and write each dynamic BAR class: plain RW, RO, W1C, doorbell, and any read-side-effect register. Repeat partial-byte writes.
5. Use a driver-owned test buffer for one DMA read and one DMA write. Compare all bytes and cover a request that splits at the configured limit and at a 4 KB boundary.
6. Keep several reads outstanding, then check Tag reuse, split Completion assembly, timeout reporting, and queue consumer movement.
7. Trigger each implemented interrupt source and confirm one acknowledgement per pending event. Repeat with MSI disabled; add the table-mask and PBA cases only when MSI-X is implemented.
8. Exercise FLR, driver disable/enable, link retrain, and the supported power transition. After each event, verify that stale Tags, descriptors, and pending interrupts are gone before the driver reinitializes the device.
9. Repeat the cold-start and warm-reset sequence used for release testing, then retain the ILA captures and Vivado reports with the matching image.

Enumeration, BAR readback, DMA data integrity, interrupt delivery, and reset recovery are separate results. Record each one independently; a successful earlier stage does not establish a later stage.

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
| PCIe wrapper, reset, link, and PM signals | `src/pcileech_pcie_a7.sv` |
| RX filter, clock crossings, and TX arbitration | `src/pcileech_pcie_tlp_a7.sv` |
| TLP, core, FIFO, and shadow interfaces | `src/pcileech_header.svh` |
| FT601 command and raw TLP routing | `src/pcileech_fifo.sv` |
| Communications clock crossing | `src/pcileech_com.sv` |
| FT601 output-channel mux | `src/pcileech_mux.sv` |
| BAR request, response, and implementations | `src/pcileech_tlps128_bar_controller.sv` |
| Zero4K contents | `ip/pcileech_bar_zero4k.coe` |
| Board pins and clocks | board-specific `.xdc` under `src/` |
| Project creation | board-specific `vivado_generate_project_*.tcl` |
| Synthesis and implementation | `vivado_build.tcl` |
