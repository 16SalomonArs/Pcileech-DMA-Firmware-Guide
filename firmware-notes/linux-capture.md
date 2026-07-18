# Linux capture

Linux is useful when a full, offset-preserving config-space capture is easier to obtain there. It is a capture supplement; the board build remains Windows/Vivado-first.

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
lspci -s "$BDF" -xxxx > "$OUT/config-256.txt"
lspci -s "$BDF" -xxxxxxx > "$OUT/config-4096.txt"
cat "/sys/bus/pci/devices/$BDF/resource" > "$OUT/resource.txt"
sudo dd if="/sys/bus/pci/devices/$BDF/config" \
    of="$OUT/config-4096.bin" bs=4096 count=1 status=progress
stat -c '%s %n' "$OUT/config-4096.bin"
sha256sum "$OUT"/* > "$OUT/SHA256SUMS"
```

The binary should be exactly 4096 bytes before it is converted into a COE. `resource.txt` records the assigned resource windows and helps determine the BAR aperture. The runtime BAR address itself is not a static firmware value.

The config-space generator in `coe-tools/` accepts an offset/DWORD CSV. Keep the Linux binary and the parsed capability list beside the generated COE so that the source of each offset remains visible.
