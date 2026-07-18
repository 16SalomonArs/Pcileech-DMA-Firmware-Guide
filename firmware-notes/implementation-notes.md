# RTL ownership notes

The source files below are identical in the three CaptainDMA FGG484 profiles at the pinned upstream revision.

## Config register bank

`src/pcileech_pcie_cfg_a7.sv` owns the PCIe core-facing register file.

```systemverilog
localparam integer RWPOS_CFG_CFGSPACE_STATUS_CL_EN = 20;
localparam integer RWPOS_CFG_CFGSPACE_COMMAND_EN   = 21;

assign ctx.cfg_dsn       = rw[127:64];
assign ctx.cfg_interrupt = rw[206];
```

The initialization task describes `rw[20]` as configuration status auto-clear and `rw[21]` as command-register auto-set. The same file uses `rw[206]` for the PCIe core interrupt signal.

`src/pcileech_fifo.sv` has a separate register bank. In that bank, `rw[203]` selects zero data for configuration reads and `rw[206]` enables PCIe-originated shadow writes:

```systemverilog
rw[202] <= 1'b1; // CFGTLP PROCESSING ENABLE
rw[203] <= 1'b1; // CFGTLP ZERO DATA
rw[204] <= 1'b1; // CFGTLP FILTER TLP FROM USER
rw[205] <= 1'b1; // PCIE BAR PIO ON-BOARD PROCESSING ENABLE
rw[206] <= 1'b0; // CFGTLP PCIE WRITE ENABLE
```

For a BRAM-backed read/write shadow, the relevant changes are `rw[203] <= 1'b0` and `rw[206] <= 1'b1`, with a WriteMask that matches the donor. Do not transfer these assignments into `pcileech_pcie_cfg_a7.sv`; the module contexts differ.

The shadow image is the stored data. The WriteMask is the per-bit write selector. `pcileech_tlps128_cfgspace_shadow.sv` captures `pcie_rx_be`, gates PCIe writes with `cfgtlp_wren`, and forms `wr_dina` from the incoming data or the existing BRAM data. RO behavior is a zero mask bit. RW behavior needs a one mask bit and an enabled byte lane. RW1C behavior needs register semantics in the owner; the mux alone does not clear status bits.

## Shadow config path

`src/pcileech_tlps128_cfgspace_shadow.sv` decodes the incoming 128-bit stream:

```systemverilog
wire pcie_rx_rden = tlps_in.tvalid && tlps_in.tuser[0]
                  && (tlps_in.tdata[31:25] == 7'b0000010);
wire pcie_rx_wren = tlps_in.tvalid && tlps_in.tuser[0]
                  && (tlps_in.tdata[31:25] == 7'b0100010);
```

It reads the `bram_pcie_cfgspace` IP and uses `drom_pcie_cfgspace_writemask` to form the write data:

```systemverilog
assign wr_dina[i] = wr_mask[i] ? wr_data_d[i] : rd_data[i];
```

The BRAM and DROM are 4 KB, 32-bit memories. Their input COE files are selected by the corresponding XCI files in the board `ip` directory.

## BAR controller

`src/pcileech_tlps128_bar_controller.sv` contains the shared TLP decoder and response mux. It instantiates:

- `pcileech_bar_impl_zerowrite4k` on BAR0;
- `pcileech_bar_impl_loopaddr` on BAR1;
- `pcileech_bar_impl_none` on BAR2 through BAR5 and the optional ROM BAR.

The checked-in PCIe XCI enables only BAR0, so the active profile uses the Zero4K BRAM. Every implementation must return data with the latency expected by the shared read engine. The source comments specify a two-clock latency for Zero4K and loopback.

The controller exports `rd_req_valid`, `rd_rsp_valid`, the request context, and the returned DWORD. Those are the useful signals when an ILA is added to the actual project. The source contains no dynamic mailbox, queue model, MSI-X table model, or PMCSR mirror.

The read path is `pcileech_pcie_tlp_a7.sv` `tlps_rx`, `pcileech_tlps128_bar_controller.sv` request classification, `rd_req_*`, the selected BAR implementation, `rd_rsp_*`, the response mux, and `tlps_bar_rsp`. The controller recognizes BAR memory read/write TLP types, passes the BAR number in `rd_req_bar`, and passes the 32-bit BAR offset in `rd_req_addr`. Zero4K uses `rd_req_addr[11:2]` and returns a full DWORD after two clocks. It has no read byte-enable merge; write byte enables reach BRAM `wea` through `wr_be`.

## Interrupt and power signals

The XCI enables MSI and disables MSI-X. `pcileech_pcie_cfg_a7.sv` maps the Xilinx core's interrupt and PM signals into its register banks, but the checked-in board RTL does not add a periodic interrupt generator or a custom PM state machine. Keep any new behavior in a separate module and update the board project sources before documenting it.

For ILA work, use the existing signals rather than inventing a parallel monitor. Config writes use `pcie_rx_wren`, `pcie_rx_addr`, `pcie_rx_data`, `pcie_rx_be`, and `bram_wr_be`. BAR reads use `rd_req_valid`, `rd_req_bar`, `rd_req_addr`, `rd_rsp_valid`, and `rd_rsp_data`. Interrupt checks use `ctx.cfg_interrupt`, `ctx.cfg_interrupt_rdy`, `ctx.cfg_interrupt_msienable`, and `ctx.cfg_interrupt_msixenable`.
