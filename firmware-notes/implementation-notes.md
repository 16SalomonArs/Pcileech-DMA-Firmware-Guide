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

## TLP transport and arbitration

`src/pcileech_pcie_a7.sv` is the wrapper around the Xilinx PCIe core. Its 64-bit RX AXI stream is converted to `IfAXIS128 tlps_rx`; the 128-bit transmit stream is converted back to the core's 64-bit interface. Both sides run on `clk_pcie`, supplied by `user_clk_out`.

`src/pcileech_pcie_tlp_a7.sv`, module `pcileech_pcie_tlp_a7`, fans `tlps_rx` into the BAR controller, shadow configuration handler, and packet filter. `pcileech_tlps128_dst_fifo` crosses accepted RX packets to `clk_sys` through `fifo_134_134_clk2`. In the other direction, `pcileech_tlps128_src_fifo` packs `dfifo.tx_data` in `clk_sys` and crosses complete 128-bit beats through `fifo_134_134_clk2_rxfifo`.

`pcileech_tlps128_sink_mux1` is the only transmit arbiter. Its fixed order is configuration response, BAR response, FIFO-injected TLP, then static TLP. It holds the selected stream until a valid last beat. A DMA packet source belongs in this arbiter; it must not bypass it or delay configuration and BAR Completions behind an unbounded request stream.

## What the BAR read engine does

`pcileech_tlps128_bar_rdengine` accepts Memory Read requests addressed to an endpoint BAR. It preserves Requester ID and Tag, splits responses larger than 128 bytes or crossing its 128-byte segment, reads one DWORD at a time from the selected BAR implementation, and builds CplD packets. This is target-side MMIO service. It does not generate outbound host-memory reads.

The write engine handles 3-DWORD and 4-DWORD Memory Write headers, carries first/last byte enables into `wr_be`, and advances `wr_addr` for each data DWORD. `pcileech_bar_impl_zerowrite4k` uses that byte enable directly on BRAM writes. A dynamic register bank should consume the same interface and keep its response context aligned to the existing two-clock read contract.

## Device engine insertion points

The following functions are absent from the pinned board RTL and need one device-level owner rather than additions to unrelated `rw[]` banks:

| Function | Existing boundary | Integration point |
|---|---|---|
| Dynamic BAR register behavior | `wr_*`, `rd_req_*`, `rd_rsp_*` in `pcileech_tlps128_bar_controller.sv` | Replace `i_bar0` with a BAR module that owns register state and side effects |
| Device command/status state | BAR writes and core state in `clk_pcie` | Keep beside the BAR register owner and queue scheduler |
| MRd/MWr generation | `IfAXIS128` TX sources in `pcileech_pcie_tlp_a7.sv` | Add one source to `pcileech_tlps128_sink_mux1` |
| Completion consumption | Cpl/CplD classification in `pcileech_tlps128_filter` | Branch owned Tags to the request table before `pcileech_tlps128_dst_fifo` |
| Tag and timeout table | 8-bit Tag in Completion header DWORD 2 | Add a `clk_pcie` free map and per-request metadata; do not use `pcileech_mux.sv` channel tags |
| Descriptor queue | No existing driver-visible queue | Add BAR queue registers, descriptor fetch, consumer update, and completion state |
| Engine interrupt | `ctx.cfg_interrupt*` in `pcileech_pcie_cfg_a7.sv` | Combine event and diagnostic requests at the current single signal owner |
| Engine reset | `rst_subsys`, FLR, Hot Reset, and link state in `pcileech_pcie_a7.sv` | Form a local `clk_pcie` engine reset and clear every outstanding transaction |

## Completion ownership

The current filter recognizes Cpl and CplD from `tlps_in.tdata[31:25]` and forwards them as raw TLPs. The destination FIFO does not decode Completion Status, Byte Count, Lower Address, or the 8-bit Tag. A request engine therefore needs its own parser and an ownership test against the live Tag table. Packets with Tags outside that table continue to the existing system FIFO.

For an owned read, retain the original address, total length, destination, received-byte count, and timeout age until the request is complete. Byte Count and Lower Address determine payload placement for the first CplD. A successful packet with the right Tag is not by itself proof that the whole Memory Read has completed.

## Queue, interrupt, reset, and power state

The existing Xilinx FIFOs are transport buffers, not descriptor rings. A driver-visible queue needs its own base, size, producer, consumer, enable, and doorbell behavior. Queue pointers and the request table should remain in `clk_pcie`; use an asynchronous FIFO for complete records that cross to `clk_sys`.

The XCI enables MSI and disables MSI-X. The current interrupt source is local `rw[206]` in `pcileech_pcie_cfg_a7.sv`. An engine event must be routed to that owner and held until `ctx.cfg_interrupt_rdy`. MSI-X also requires a BAR table and PBA, neither of which appears in `pcileech_tlps128_bar_controller.sv`.

`rst_subsys` includes board reset, PCIe `user_reset_out`, and the software subsystem reset. `ctx.cfg_received_func_lvl_rst` and `ctx.pl_received_hot_rst` are exposed but are not included in a custom engine reset because no such engine exists. New state must clear on those events, stop issuing on link loss, and observe `ctx.cfg_pmcsr_powerstate`. The PM control wires in `rw[208:214]` expose the core interface; they do not implement device D-state behavior.

The `initial_rx` word in `pcileech_com.sv` brings the PCILeech transport out of its startup reset. Driver initialization is separate and must be derived from the actual BAR access sequence: queue programming, interrupt setup, enable/doorbell, ready status, DMA exchange, and acknowledgement.
