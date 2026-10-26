# Hardware-profile porting guide

How to capture the per-card data that `profiles/<card>.h` expects.

The Windows UEFI application refuses to start FWSEC or the Booter unless all
of the following match **your** board:

1. PCI vendor / device ID (`0x10de:0x2684` for RTX 4090, …)
2. PCI subsystem (VGA BIOS SubVendor:SubDevice) — differs between AIBs
3. BAR0 chip ID register (PMC_BOOT_0) — `0x192000a1` AD102, `0x194000a1` AD104
4. 19 cold-entry BAR0 words (WPR / FEAT / SS0 / SS1 / cluster registers)
5. FWSEC geometry inside the board ROM
6. VBIOS ROM SHA-256
7. Asset filenames, sizes and SHA-256 (integrity only, not board-specific)

Any mismatch halts before a single GPU register is written. Do not disable
these checks.

## Step 1 — PCI IDs

```bash
lspci | grep -Ei 'vga|3d|nvidia'          # find the BDF, e.g. 01:00.0
lspci -n -s 01:00.0                        # vendor:device
lspci -vv -s 01:00.0 | grep -i subsystem   # VGA BIOS subsystem
```

Windows: GPU-Z main tab, or

```powershell
Get-PnpDevice | Where-Object { $_.FriendlyName -match 'NVIDIA' } | ForEach-Object {
  Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_HardwareIds'
}
```

## Step 2 — Cold BAR0 + PCI config dump (before the driver loads)

The 19 cold-entry words change once `nvidia.ko` / `nvlddmkm.sys` has bound the
card in this boot, and reset only on a real power cycle (power off, wait ten
seconds). So read them on a cold boot, before any GPU driver.

Ways to get a pre-driver window:

- Linux with the NVIDIA modules blacklisted on the kernel command line:
  `modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nvidia_peermem`
- The read-only probe in `src/diagnostic/` (how the MSI 4070 Ti capture was done)
- `tools/capture_ad102_cold.py` at the repo root (RTX 4090 / AD102): builds and
  loads `diagnostics/peek/gpu_peek.ko`, parses its output, dumps PCI config
  space and the ROM, and writes a filled `profile.h` plus the 19-word
  admission table. It refuses a warm read unless `--allow-warm` is passed.

```bash
sudo ./tools/capture_ad102_cold.py -d 0000:01:00.0 -o captures/4090
# replay a saved log instead (no root, no module):
./tools/capture_ad102_cold.py --from-dmesg saved.log
```

For a non-4090 card the same data can be read by hand:

```bash
BDF=01:00.0
setpci -s $BDF COMMAND=0x0003
BASE=$(setpci -s $BDF BASE_ADDRESS_0 | cut -d= -f2)
for off in 0x000000 0x118128 0x118234 0x110100 0x1fa824 0x1fa828 \
           0x1fa7cc 0x1fa7c4 0x9a0148 0x823804 0x823818 0x1183a4 \
           0x625f04 0x1fa7c8 0x1fa82c 0x1fa830 0x824148 0x8241e0; do
  v=$(devmem2 $(($BASE + $off)) w 2>/dev/null | grep -oP 'Value at.*: \K0x[0-9a-f]+')
  [ -n "$v" ] && printf "%-8s %s\n" $off $v
done
```

Copy the readbacks into your profile. Do not guess.

The authoritative admission table is **not** the `profiles/*.h` header: it is
the `offsets[]` / `values[]` pair inside `windows/ad104-msi/profile.c` that
`Registers()` walks, plus the PCI config words asserted in `Config()`. A new
board needs those arrays replaced too; the capture tool writes them out as
`cold-entry.txt`.

## Step 3 — VBIOS ROM and hash

```bash
ROM=/sys/bus/pci/devices/0000:01:00.0/rom
dd if=$ROM of=prom.bin bs=1 count=$(stat -c%s $ROM) status=none
sha256sum prom.bin     # -> PROFILE_PROM_HASH
```

FWSEC geometry is parsed by the application at boot; pin the parsed values in
the profile as a second check.

## Step 4 — Build

```powershell
cd src
.\Build-Experimental.ps1 -Python python -Define "GPU_PROFILE_AD102_RTX4090"
# or a manual capture with no header:
#   -DGPU_PROFILE_PCI_DEVICE=0x2684 -DGPU_PROFILE_SUBSYSTEM=0xXXXXXXXX
```

Run the admission test driver before touching hardware:

```powershell
.\Test-Experimental.ps1 -IncludeCore -Prom prom.bin -Assets build\assets
```

## Pitfalls

| Symptom | Cause |
|---|---|
| `admission: PCI device mismatch` | wrong `GPU_PROFILE_PCI_DEVICE` |
| `FWSEC geometry mismatch` | VBIOS changed; recapture Step 3 |
| cold BAR0 mismatch on one offset | driver already bound this boot; full power off, wait 10 s |
| SS1 mismatch on AD102 | AD102 cold SS1 is `0x7`; AD104 is `0x1` — don't copy across chips |
| marker `0x67b00001` but selector writes rejected | FEAT PLM did not open; regenerate assets with `make assets` |
| BSOD on driver load after FLR | WPR2 still enabled; check boot log, power-cycle |

## Adding a new profile

1. Copy `profiles/ad102-4090.h` to `profiles/<card>.h` and replace every TODO.
2. Add a branch to `src/port.h`, or use `-DGPU_PROFILE_PCI_DEVICE=…`.
3. Add the PCI ID to `src/vendor/arch_610.h` (and to `gpu_unlock_is_ada_pci()`).
4. Rebuild, run the test driver, then do a cold-boot regression:
   unlock → Windows → long workload → power off → confirm stock state returns.

Never publish your VBIOS ROM or raw register dumps: they contain board-unique
serial data. Share hashes and readbacks only.
