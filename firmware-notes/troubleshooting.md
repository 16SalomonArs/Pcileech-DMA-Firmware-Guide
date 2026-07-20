# Troubleshooting

Find the first layer that diverges. A driver symptom is not a reason to change the donor IDs before reading config space again.

| Symptom | Check | Action |
|---|---|---|
| Vivado selects the wrong device | `get_property PART [current_project]` and the board folder | Start over with the matching generator and XDC |
| Project generation cannot find a source | `origin_dir`, current directory, and the generator filename | Run the board's `vivado_generate_project_captaindma_*.tcl` from its own folder |
| Config data after `0x40` is zero | `rw[203]`, `bram_pcie_cfgspace.xci`, and the COE path | Select BRAM data and regenerate output products |
| Config writes do not stick | `rw[206]` in `pcileech_fifo.sv`, WriteMask, and actual capability offsets | Enable only the intended writes and rebuild the DROM |
| VID/DID changes after a write | WriteMask DWORD `0x000` | Keep the identity DWORD read-only |
| BAR0 read has no completion | `bar_en`, BAR0 XCI setting, `rd_req_valid`, `rd_rsp_valid` | Keep the BAR enabled and trace the shared response path |
| POST stops before Windows | Board marking, FPGA part, XDC, stock image, and selected BIN | Use the matching board generator and restore the stock image before changing RTL |
| Device Manager reports Code 10 or Code 43 | Config capability chain, BAR0 readback, Command, MSI, PMCSR, and the first driver MMIO access | Fix the first divergent layer; Zero4K has no device-specific state machine |
| A write changes an unintended byte lane | TLP byte enable, `wr_be`, and the WriteMask DWORD | Compare all four lanes and the donor field type before editing the mask |
| BAR data is returned internally but no Completion is visible | `rd_rsp_valid`, `rd_rsp_ctx`, response mux, `tlps_bar_rsp`, and `tlps_out` | Keep the selected BAR latency at two clocks and trace the response FIFO |
| MSI is enabled in config space but no request is seen | `ctx.cfg_interrupt_msienable`, `ctx.cfg_interrupt_rdy`, and `ctx.cfg_interrupt` | Check the core interrupt handshake and the donor MSI fields |
| PMCSR or Command readback is wrong | Capability base, `rw[20]`, `rw[21]`, `ctx.cfg_mgmt_*`, and `cfg_mgmt_byte_en` | Keep core-owned fields on the core management path |
| Host blue-screens during config or BAR access | WriteMask, RW1C behavior, byte enables, out-of-range BAR accesses, and timing reports | Stop at the first malformed response or timing violation |
| ILA shows a request without a response | `rd_req_valid`, `rd_req_bar`, `rd_req_addr`, `rd_rsp_valid`, and `rd_rsp_data` | Check `i_bar0`, address alignment, BRAM enable, and the shared latency |
| BAR0 returns old data | `ip/pcileech_bar_zero4k.coe` and `bram_bar_zero4k.xci` | Replace the board-local COE and regenerate that IP |
| BAR0 works only below `0x1000` | `pcileech_bar_impl_zerowrite4k` address range | Add the required RTL or keep the device within the 4 KB model |
| MSI configuration does not match the donor | XCI MSI fields and capability readback | Align the PCIe IP and WriteMask at the donor offset |
| MSI-X is present unexpectedly | `MSIx_Enabled` in `ip/pcie_7x_0.xci` | Keep it disabled unless a table/PBA implementation is part of the RTL |
| A Memory Read never completes | Issued Tag, Cpl/CplD Tag, Completion Status, Byte Count, Lower Address, and timeout counter | Keep the Tag live until all requested bytes arrive or the request enters its timeout path |
| Read data is shifted after a split Completion | Original address, first byte enable, Lower Address, Byte Count, and bytes already received | Place the first returned byte from Lower Address and advance by accepted payload bytes |
| The Tag pool eventually stalls | Free bitmap, request table, timeout quarantine bitmap, and reset cleanup | Free a Tag once after full success or non-success Completion; keep a timed-out Tag quarantined until reset or the guard interval expires |
| Queue consumer stops moving | Producer/consumer indices, ring size, descriptor status, request table, and completion event | Advance the consumer after all work for that descriptor is complete, not when it is fetched |
| Doorbell works only on a full DWORD write | `wr_addr`, `wr_be`, `wr_data`, and the doorbell byte lane | Decode the enabled byte lane and generate a single-cycle side effect from the accepted BAR write |
| DMA starts before the driver is ready | `ctx.cfg_command`, queue-valid state, power state, link state, and enable write | Require the complete initialization handshake and Bus Master Enable before issuing a request |
| MSI repeats or disappears under backpressure | Pending-event latch, `ctx.cfg_interrupt`, and `ctx.cfg_interrupt_rdy` | Keep the event pending until the core acknowledges it and clear it once on that handshake |
| DMA final beat changes while the core is not ready | TX mux `id`, `tvalid`, `tready`, `tlast`, and DMA `has_data` | Advance the mux only on an accepted last beat and hold the selected stream stable under backpressure |
| FLR leaves an old descriptor active | `ctx.cfg_received_func_lvl_rst`, queue state, Tag table, and pending interrupt | Include FLR in the device-engine reset event and require queue programming again |
| Link retrains but DMA remains stopped | `ctx.pl_phy_lnk_up`, `ctx.pl_ltssm_state`, queue-valid state, and driver writes | Stop on link loss, clear transport state, then wait for link and driver reinitialization |
| D3 entry leaves requests in flight | `ctx.cfg_pmcsr_powerstate`, `ctx.cfg_trn_pending`, queue issue, and interrupt state | Stop new work before the transition and apply the device's defined drain or abort behavior |
| WNS/TNS or endpoint checks fail | `reports/timing_summary.rpt` and `reports/check_timing.rpt` | Fix clocks, constraints, or RTL before flashing |
| CH347 cannot identify the board | Physical board, adapter orientation, driver, and image profile | Return to the stock image and the exact board directory |
| Windows sees an old image after a power cycle | BIN path and flash-tool operation | Confirm the programmer wrote persistent flash, then power-cycle again |

## Useful checks in Vivado Tcl

```tcl
puts [get_property PART [current_project]]
puts [get_property STATUS [get_runs synth_1]]
puts [get_property STATUS [get_runs impl_1]]
open_run impl_1
check_timing -verbose
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10
```

For an ILA, trigger config writes on `pcie_rx_wren`, BAR reads on `rd_req_valid`, and interrupt checks on `ctx.cfg_interrupt`. The checked-in sources expose the useful signals in `pcileech_tlps128_cfgspace_shadow.sv`, `pcileech_tlps128_bar_controller.sv`, and `pcileech_pcie_cfg_a7.sv`; add the ILA to the generated project rather than to the source checkout's documentation only.

Do not treat a generated BIT or BIN as proof of PCIe enumeration. Keep the build report, config readback, BAR readback, and flash record as separate pieces of evidence.
