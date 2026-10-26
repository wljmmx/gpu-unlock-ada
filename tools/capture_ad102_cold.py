#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Capture the cold-boot BAR0 state of an RTX 4090 (AD102, 10de:2684).

Why this exists
---------------
windows/ad104-msi/ refuses to start FWSEC unless the card's PCI identity,
cold-entry registers, PROM hash and FWSEC geometry match a pinned profile.
That profile only exists for one MSI RTX 4070 Ti. Porting the Windows app to a
4090 therefore needs a capture from *your* card, taken before any GPU driver
has bound it in this power cycle.

This script does not write to the GPU. It builds and loads the read-only
sampler diagnostics/peek/gpu_peek.ko (one ioread32 per word, no firmware, no
reset, no config-space write), parses its dmesg output, dumps PCI config space
and the VBIOS ROM, and emits:

  capture.json   every raw value plus provenance
  registers.txt  the kernel log excerpt, sanitised
  profile.h      the defines for windows/ad104-msi/profiles/ad102-4090.h
  cold-entry.txt the 19-word admission table used by profile.c

Getting a genuinely cold read
-----------------------------
The values reset only on a real power cycle (power off, wait ten seconds), and
nvidia/nvlddmkm overwrites them once it probes the card. Boot with the NVIDIA
driver excluded, e.g.

  # /etc/default/grub
  GRUB_CMDLINE_LINUX="modprobe.blacklist=nvidia,nvidia_drm,nvidia_modeset,nvidia_uvm,nvidia_peermem"

then run this script as root. The script refuses a warm read by default.

Usage
-----
  sudo ./tools/capture_ad102_cold.py                      # auto-detect 10de:2684
  sudo ./tools/capture_ad102_cold.py -d 0000:01:00.0 -o captures/4090
  ./tools/capture_ad102_cold.py --from-dmesg saved.log     # replay, no root

Exit codes: 0 captured, 2 not a cold read, 3 capture failed, 4 usage error.
"""
import argparse
import glob
import json
import os
import platform
import re
import subprocess
import sys
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOOLS_DIR)
PEEK_DIR = os.path.join(REPO_DIR, "diagnostics", "peek")

# PCI identity of the card this script profiles.
AD102_VENDOR = 0x10DE
AD102_DEVICE = 0x2684
AD102_CHIP_ID = 0x192000A1          # PMC_BOOT_0, from rtx4090-register-report.md

# Cold values published for AD102 in docs/evidence/rtx4090/registers.txt and
# rtx4090-register-report.md. Anything not listed here has no published
# reference: it is recorded, not asserted.
AD102_COLD_REF = {
    0x000000: (AD102_CHIP_ID, "PMC_BOOT_0 chip id"),
    0x001FA824: (0x1FFFFE00, "WPR2 lo"),
    0x001FA828: (0x00000000, "WPR2 hi"),
    0x00823804: (0xFFFFFF8F, "FEAT_OVR_PLM gate"),
    0x00823814: (0x00000233, "FEAT_READOUT_0"),
    0x00823818: (0x00410080, "FEAT_READOUT_1"),
    0x0082381C: (0x44023025, "SS0 cold"),
    0x00823820: (0x00000007, "SS1 cold"),
    0x001FA7CC: (0x0004CB8F, "WPR_CFG PLM"),
    0x001FA7C4: (0x0004CB8F, "WPR PLM"),
    0x009A0148: (0xFFFFFF0F, "FBPA PLM"),
    0x00820000: (0xE0040000, "FUSECTRL"),
    0x008200FC: (0xFFFFFFFF, "FUSE_SS_PLM"),
    0x0082038C: (0x00000001, "SECURE_FEAT_OVR_QUADRO_WR_SECURE"),
    0x0082059C: (0x00000000, "FUSE_SS_FFMA"),
    0x008207D4: (0x00000000, "FUSE_SS_FMLA16"),
    0x008207D8: (0x00000001, "FUSE_SS_FMLA32"),
    0x008207DC: (0x00000000, "FUSE_SS_IMLA0"),
    0x008207E0: (0x00000000, "FUSE_SS_IMLA1"),
    0x008207E4: (0x00000001, "FUSE_SS_IMLA2"),
    0x008207E8: (0x00000000, "FUSE_SS_IMLA3"),
    0x008207EC: (0x00000001, "FUSE_SS_IMLA4"),
    0x00409664: (0xBADF5040, "FECS selector copy"),
    0x00409668: (0xBADF5040, "FECS readout copy"),
    0x00504204: (0x00000005, "SM_ISSUE_RATE_MODIFIER"),
    0x00824148: (0x00000001, "Booter ucode fuse"),
    0x008241E0: (0x00000001, "FWSEC ucode fuse"),
}

# The 19-word admission table windows/ad104-msi/profile.c Registers() walks, in
# the same order, so the generated snippet drops straight in.
ADMISSION_OFFSETS = [
    0x000000, 0x118128, 0x118234, 0x110100, 0x1FA824, 0x1FA828, 0x1FA7CC,
    0x1FA7C4, 0x9A0148, 0x823804, 0x823814, 0x823818, 0x1183A4, 0x625F04,
    0x1FA7C8, 0x1FA82C, 0x1FA830, 0x824148, 0x8241E0,
]

REG_RE = re.compile(r"gpu_peek: 0x([0-9a-fA-F]+)\s+(.+?)\s+= 0x([0-9a-fA-F]+)\s*$")
DRIVER_RE = re.compile(r"gpu_peek: driver=(\S+)(?:\s+BAR0=(\S+)\s+len=(\S+))?\s+command=(\S+)")
SUMMARY_RE = re.compile(r"gpu_peek: summary (.+)$")
PROM_RE = re.compile(r"gpu_peek: PROM @ 0x300000 bytes=(\d+) sig=(0x[0-9a-fA-F]+)")
FWSEC_RE = re.compile(
    r"FWSEC-FRTS parsed from PROM! ucode_id=(\d+) engine_mask=(0x[0-9a-fA-F]+) "
    r"img_off=(0x[0-9a-fA-F]+) img_size=(0x[0-9a-fA-F]+) imem=(0x[0-9a-fA-F]+) "
    r"dmem=(0x[0-9a-fA-F]+) sig_count=(\d+) sig_versions=(0x[0-9a-fA-F]+)")


class CaptureError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def parse_snapshots(text):
    """Split a gpu_peek log into one snapshot per 'driver=' line.

    A snapshot is {"driver", "bar0", "len", "command", "registers", "summary"}.
    Lines from other modules are ignored, so a full dmesg can be fed directly.
    """
    snaps, cur = [], None

    def new_snapshot(driver, bar0, length, command):
        def as_int(text):
            try:
                return int(text, 0) if text else None
            except (TypeError, ValueError):
                return None
        return {"driver": driver, "bar0": as_int(bar0), "len": as_int(length),
                "command": as_int(command), "registers": {}, "summary": {}}

    for raw in text.splitlines():
        line = raw.rstrip()
        m = DRIVER_RE.search(line)
        if m:
            if cur and (cur["registers"] or cur["summary"]):
                snaps.append(cur)
            cur = new_snapshot(m.group(1), m.group(2), m.group(3), m.group(4))
            continue
        if cur is None:
            continue
        m = REG_RE.search(line)
        if m:
            cur["registers"][int(m.group(1), 16)] = {
                "name": m.group(2).strip(), "value": int(m.group(3), 16)}
            continue
        m = SUMMARY_RE.search(line)
        if m:
            for token in m.group(1).split():
                if "=" in token:
                    key, val = token.split("=", 1)
                    try:
                        cur["summary"][key] = int(val, 0)
                    except ValueError:
                        cur["summary"][key] = val
    if cur and (cur["registers"] or cur["summary"]):
        snaps.append(cur)
    return snaps


def parse_prom(text):
    """Return the PROM block gpu_peek printed (bytes, signature, FWSEC fields)."""
    prom = {}
    m = PROM_RE.search(text)
    if m:
        prom["bytes_mapped"] = int(m.group(1))
        prom["signature"] = int(m.group(2), 16)
    m = FWSEC_RE.search(text)
    if m:
        prom["fwsec"] = {
            "ucode_id": int(m.group(1)),
            "engine_mask": int(m.group(2), 16),
            "image_off": int(m.group(3), 16),
            "image_size": int(m.group(4), 16),
            "imem_size": int(m.group(5), 16),
            "dmem_size": int(m.group(6), 16),
            "sig_count": int(m.group(7)),
            "sig_versions": int(m.group(8), 16),
        }
    return prom


def select_cold_snapshot(snaps):
    """Prefer a snapshot whose selectors are demonstrably untouched."""
    for snap in snaps:
        regs, summ = snap["registers"], snap["summary"]
        plm = regs.get(0x00823804, {}).get("value")
        ss0 = regs.get(0x0082381C, {}).get("value")
        if plm == 0xFFFFFF8F and ss0 not in (None, 0xFFFFFFFF, 0x88888888):
            return snap
    return snaps[0] if snaps else None


def verdict(snap, prom):
    """Classify the snapshot as cold / warm / unusable, with the reasons."""
    reasons, cold = [], True
    regs, summ = snap["registers"], snap["summary"]
    plm = regs.get(0x00823804, {}).get("value")
    ss0 = regs.get(0x0082381C, {}).get("value")
    ss1 = regs.get(0x00823820, {}).get("value")

    if snap["driver"] not in ("none", "unknown"):
        cold = False
        reasons.append("driver '%s' is bound to the card" % snap["driver"])
    if plm == 0xFFFFFFFF:
        cold = False
        reasons.append("FEAT_OVR_PLM is already open (0xffffffff)")
    elif plm != 0xFFFFFF8F:
        cold = False
        reasons.append("FEAT_OVR_PLM is %s, expected 0xffffff8f" %
                       ("absent" if plm is None else "0x%08x" % plm))
    if ss0 == 0x88888888:
        cold = False
        reasons.append("SS0 already holds the unlocked value")
    if ss1 == 0x8:
        cold = False
        reasons.append("SS1 already holds the unlocked value")
    if summ.get("wpr2_up"):
        cold = False
        reasons.append("WPR2 is up: firmware already initialised this boot")
    if summ.get("plm_open"):
        cold = False
        reasons.append("summary reports plm_open=1")

    chip = regs.get(0x000000, {}).get("value")
    if chip is not None and chip != AD102_CHIP_ID:
        reasons.append("chip id is 0x%08x, AD102 reference is 0x%08x" %
                       (chip, AD102_CHIP_ID))
    if prom.get("signature") not in (None, 0xAA55):
        reasons.append("PROM signature is 0x%04x, not 0xaa55" % prom["signature"])

    state = "cold" if cold else "warm"
    return state, reasons


def compare_reference(snap):
    """Check captured words against the published AD102 cold values."""
    rows = []
    for off, (want, name) in sorted(AD102_COLD_REF.items()):
        entry = snap["registers"].get(off)
        got = entry["value"] if entry else None
        rows.append({"offset": off, "name": name, "expected": want,
                     "actual": got,
                     "match": got == want if got is not None else None})
    return rows


# --------------------------------------------------------------------------
# local hardware reads (Linux sysfs)
# --------------------------------------------------------------------------

def sysfs_path(bdf):
    return "/sys/bus/pci/devices/" + bdf


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def read_identity(bdf):
    base = sysfs_path(bdf)
    ident = {}
    for key, path in (("vendor", "vendor"), ("device", "device"),
                      ("subsystem_vendor", "subsystem_vendor"),
                      ("subsystem_device", "subsystem_device"),
                      ("class", "class"), ("revision", "revision")):
        val = read_text(os.path.join(base, path))
        ident[key] = int(val, 16) if val else None
    return ident


def read_driver(bdf):
    link = os.path.join(sysfs_path(bdf), "driver")
    return os.path.basename(os.path.realpath(link)) if os.path.exists(link) else None


def read_resource0(bdf):
    path = os.path.join(sysfs_path(bdf), "resource")
    text = read_text(path)
    if not text:
        return None
    first = text.splitlines()[0].split()
    if len(first) < 2:
        return None
    start, end = int(first[0], 16), int(first[1], 16)
    return {"start": start, "end": end, "len": end - start + 1}


def read_config_space(bdf, dwords=64):
    """First 256 bytes of PCI config space, as dwords (what profile.c walks)."""
    path = os.path.join(sysfs_path(bdf), "config")
    try:
        with open(path, "rb") as f:
            raw = f.read(dwords * 4)
    except OSError as exc:
        raise CaptureError("cannot read %s: %s (run as root)" % (path, exc))
    return ["0x%08x" % int.from_bytes(raw[i:i + 4], "little")
            for i in range(0, len(raw) - 3, 4)]


def dump_rom(bdf, limit=1024 * 1024):
    """Read the VBIOS through sysfs /rom; returns (bytes, sha256 hex)."""
    import hashlib
    path = os.path.join(sysfs_path(bdf), "rom")
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "wb") as f:      # writing 1 enables the ROM aperture
            f.write(b"1")
    except OSError as exc:
        raise CaptureError("cannot enable %s: %s (run as root)" % (path, exc))
    try:
        size = os.path.getsize(path) or limit
        with open(path, "rb") as f:
            data = f.read(min(size, limit))
    finally:
        try:
            with open(path, "wb") as f:
                f.write(b"0")
        except OSError:
            pass
    if not data or data[0] | (data[1] << 8) != 0xAA55:
        return data, None
    return data, hashlib.sha256(data).hexdigest()


def find_ad102():
    """Locate an NVIDIA display function with device id 0x2684/0x2685."""
    hits = []
    for dev in glob.glob("/sys/bus/pci/devices/*"):
        try:
            vendor = int(read_text(os.path.join(dev, "vendor")) or "0", 16)
            device = int(read_text(os.path.join(dev, "device")) or "0", 16)
        except ValueError:
            continue
        if vendor == AD102_VENDOR and device in (AD102_DEVICE, 0x2685):
            hits.append(os.path.basename(dev))
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CaptureError("no NVIDIA 10de:2684 display function found")
    raise CaptureError("several candidate cards (%s); pass --device"
                       % ", ".join(hits))


# --------------------------------------------------------------------------
# gpu_peek invocation
# --------------------------------------------------------------------------

def build_peek(peek_dir):
    ko = os.path.join(peek_dir, "gpu_peek.ko")
    print("building %s ..." % ko)
    proc = subprocess.run(["make", "-C", peek_dir], capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(ko):
        raise CaptureError(
            "module build failed:\n%s\nHint: install the headers for your "
            "kernel (linux-headers-$(uname -r)), or pass LLVM=1 when the kernel "
            "was built with clang: 'make LLVM=1 -C %s'." %
            ((proc.stdout + proc.stderr).strip(), peek_dir))
    return ko


def read_dmesg(since=None):
    cmd = ["dmesg"]
    if since is not None:
        cmd += ["--since", time.strftime("%Y-%m-%d %H:%M:%S",
                                         time.localtime(since))]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CaptureError("dmesg failed: %s" % proc.stderr.strip())
    return proc.stdout


def run_peek(ko, bdf):
    started = int(time.time()) - 2
    params = ["target=" + bdf, "cluster=1", "permissions=1", "prom=1", "sec2=1"]
    subprocess.run(["insmod", ko] + params, check=True)
    time.sleep(0.5)
    try:
        log = read_dmesg(started)
    finally:
        subprocess.run(["rmmod", "gpu_peek"], check=False)
    lines = [ln for ln in log.splitlines()
             if "gpu_peek" in ln or "FW_SEC" in ln or "AD102" in ln]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def hex32(value):
    """Format a captured word, or a TODO marker when it was not sampled."""
    if value is None:
        return "0x00000000u"
    return "0x%08xu" % value


def emit_profile(meta, snap, prom):
    regs = snap["registers"]
    ident = meta["identity"]

    def cold(off, macro, note=""):
        val = regs.get(off, {}).get("value")
        comment = "not sampled" if val is None else note
        line = "#define %-32s %s" % (macro, hex32(val))
        if comment:
            line += "  /* %s */" % comment
        return line

    fw = prom.get("fwsec") or {}
    out = []
    add = out.append
    add("/* SPDX-License-Identifier: GPL-2.0-only */")
    add("/*")
    add(" * Generated by tools/capture_ad102_cold.py on %s" % meta["captured_at"])
    add(" * Source: %s (%s) driver=%s" % (meta["bdf"], meta["host"], snap["driver"]))
    add(" * Verdict: %s" % meta["verdict"])
    add(" *")
    add(" * This is one card's cold read. Review every value before trusting it")
    add(" * for another board; subsystem ID, PROM hash and several cold words")
    add(" * differ between AIBs and VBIOS revisions.")
    add(" */")
    add("#ifndef PROFILE_AD102_4090_H")
    add("#define PROFILE_AD102_4090_H")
    add("")
    add("/* ---- PCI identity ---- */")
    add("#define PROFILE_PCI_VENDOR    0x%04x%s" %
        (ident.get("vendor") or 0, "" if ident.get("vendor") else "  /* TODO */"))
    add("#define PROFILE_PCI_DEVICE    0x%04x%s" %
        (ident.get("device") or 0, "" if ident.get("device") else "  /* TODO */"))
    add("#define PROFILE_PCI_SUBSYSTEM 0x%04x%04xu%s" %
        (ident.get("subsystem_device") or 0, ident.get("subsystem_vendor") or 0,
         "" if ident.get("subsystem_device") else "  /* TODO */"))
    add("")
    add("/* ---- BAR0 ---- */")
    if meta.get("resource0"):
        add("#define PROFILE_BAR0_SIZE_BYTES 0x%xu  /* captured resource0 length */"
            % meta["resource0"]["len"])
        add("#define PROFILE_BAR0_BASE        0x%xULL  /* firmware-assigned; your boot may differ */"
            % meta["resource0"]["start"])
    else:
        add("#define PROFILE_BAR0_SIZE_BYTES 0x1000000u  /* TODO: verify */")
        add("#define PROFILE_BAR0_BASE        0x80000000ULL  /* TODO: capture */")
    add("#define PROFILE_PCI_COMMAND_EXPECTED 0x%04xu  /* MEM+MASTER as captured */" %
        ((snap["command"] & 0xFFFF) if isinstance(snap["command"], int) else 0x0003))
    add("")
    add("/* ---- Cold-entry BAR0 words (windows profile.c Registers() table) ---- */")
    add(cold(0x000000, "PROFILE_PMC_BOOT_0_REF", "chip id"))
    add(cold(0x118128, "PROFILE_GFW_PLM"))
    add(cold(0x118234, "PROFILE_GFW_BOOT"))
    add(cold(0x110100, "PROFILE_GFW_CPUCTL"))
    add(cold(0x1FA824, "PROFILE_WPR_LO_EXPECTED"))
    add(cold(0x1FA828, "PROFILE_WPR_HI_EXPECTED"))
    add(cold(0x1FA7CC, "PROFILE_WPR_CFG_PLM_COLD"))
    add(cold(0x1FA7C4, "PROFILE_WPR_PLM_COLD"))
    add(cold(0x9A0148, "PROFILE_FBPA_PLM_COLD"))
    add(cold(0x823804, "PROFILE_FEAT_PLM_COLD"))
    add(cold(0x823814, "PROFILE_FEAT_READOUT_0_COLD"))
    add(cold(0x823818, "PROFILE_FEAT_READOUT_1_COLD"))
    add(cold(0x1183A4, "PROFILE_FB_SIZE_MB"))
    add(cold(0x625F04, "PROFILE_VGA_BASE"))
    add(cold(0x1FA7C8, "PROFILE_MMU_PLM"))
    add(cold(0x1FA82C, "PROFILE_MMU_LO"))
    add(cold(0x1FA830, "PROFILE_MMU_HI"))
    add(cold(0x824148, "PROFILE_BOOTER_UCODE_FUSE"))
    add(cold(0x8241E0, "PROFILE_FWSEC_UCODE_FUSE"))
    add("")
    add("/* ---- Speed select ---- */")
    add(cold(0x82381C, "PROFILE_FEAT_SS0_COLD"))
    add(cold(0x823820, "PROFILE_FEAT_SS1_COLD"))
    add("#define PROFILE_SS0_UNLOCK 0x88888888u")
    add("#define PROFILE_SS1_UNLOCK 0x00000008u")
    add("")
    add("/* ---- PROM / VBIOS ---- */")
    add("#define PROFILE_PROM_SIZE %su" %
        ("0x%x" % meta["prom"]["bytes"] if meta["prom"].get("bytes") else "0x0"))
    add('#define PROFILE_PROM_HASH "%s"' % (meta["prom"].get("sha256") or
                                            "0" * 64 + '"  /* TODO: ROM unreadable'))
    add("")
    add("/* ---- FWSEC geometry parsed from this board's PROM by gpu_peek ---- */")
    if fw:
        add("#define PROFILE_FWSEC_IMAGE_OFF     0x%05xu" % fw["image_off"])
        add("#define PROFILE_FWSEC_IMAGE_SIZE    0x%05xu" % fw["image_size"])
        add("#define PROFILE_FWSEC_IMEM_SIZE     0x%05xu" % fw["imem_size"])
        add("#define PROFILE_FWSEC_DMEM_SIZE     0x%05xu" % fw["dmem_size"])
        add("#define PROFILE_FWSEC_UCODE_ID      %uu" % fw["ucode_id"])
        add("#define PROFILE_FWSEC_ENGINE_MASK   0x%04xu" % fw["engine_mask"])
        add("#define PROFILE_FWSEC_SIG_COUNT     %uu" % fw["sig_count"])
        add("#define PROFILE_FWSEC_SIG_VERSIONS  0x%xu" % fw["sig_versions"])
    else:
        add("/* gpu_peek did not parse FWSEC from the PROM; re-run with prom=1 */")
    add("/* TODO: pkc_off, interface_off, sig_off, sig_bytes, imem/ dmem PA are")
    add(" *      not printed by gpu_peek; read them from windows/ad104-msi/")
    add(" *      tools/fwsec_inspect.c against your dumped ROM. */")
    add("")
    add("/* ---- Assets (shared by every Ada card; pin your generated files) ---- */")
    add('#define PROFILE_ASSET_BOOTER       "AD102-ASSETS/booter_load_ad102.bin"')
    add("#define PROFILE_ASSET_BOOTER_SIZE  0u  /* TODO */")
    add('#define PROFILE_ASSET_BOOTER_HASH  "%s"' % ("0" * 64))
    add('#define PROFILE_ASSET_PAYLOAD      "AD102-ASSETS/v67-ad102-610.43.03-four-plm.bin"')
    add("#define PROFILE_ASSET_PAYLOAD_SIZE 0u  /* TODO */")
    add('#define PROFILE_ASSET_PAYLOAD_HASH "%s"' % ("0" * 64))
    add("")
    add("#define PROFILE_EXPECTED_MARKER             0x67b00001u")
    add("#define PROFILE_EXPECTED_FEAT_PLM_OPEN      0xffffffffu")
    add("#define PROFILE_EXPECTED_WPR_PLM_OPEN       0xffffffffu")
    add("#define PROFILE_EXPECTED_FEAT_PLM_AFTER_FLR 0xffffffffu")
    add("")
    add("#endif /* PROFILE_AD102_4090_H */")
    return "\n".join(out) + "\n"


def emit_admission_table(snap):
    """Emit the profile.c arrays for the captured card."""
    regs = snap["registers"]
    offs, vals = [], []
    for off in ADMISSION_OFFSETS:
        val = regs.get(off, {}).get("value")
        offs.append("0x%x" % off if off else "0")
        vals.append("0x%x" % val if val is not None else "0x0 /* TODO */")
    out = ["/* windows/ad104-msi/profile.c -- replace the 19-entry table.",
           " * SS0/SS1 are captured below the table: the existing code reads",
           " * 0x82381c/0x823820 separately and compares SS1 against 1 for AD104;",
           " * AD102 cold SS1 is 7, so that literal must become PROFILE_FEAT_SS1_COLD. */",
           "static const UINT32 offsets[]={%s};" % ",".join(offs),
           "static const UINT32 values[]={%s};" % ",".join(vals)]
    return "\n".join(out) + "\n"


def write_outputs(outdir, meta, snap, prom, log, rows):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "registers.txt"), "w") as f:
        f.write(log)
    with open(os.path.join(outdir, "profile.h"), "w") as f:
        f.write(emit_profile(meta, snap, prom))
    with open(os.path.join(outdir, "cold-entry.txt"), "w") as f:
        f.write(emit_admission_table(snap))
    record = {
        "tool": os.path.basename(__file__),
        "captured_at": meta["captured_at"],
        "host": meta["host"],
        "kernel": meta["kernel"],
        "cmdline": meta["cmdline"],
        "bdf": meta["bdf"],
        "identity": meta["identity"],
        "driver": meta["driver"],
        "resource0": meta.get("resource0"),
        "pci_config_dwords": meta.get("pci_config_dwords"),
        "verdict": meta["verdict"],
        "verdict_reasons": meta["verdict_reasons"],
        "snapshot": {"driver": snap["driver"], "command": snap["command"],
                     "registers": {"0x%06x" % k: "0x%08x" % v["value"]
                                   for k, v in sorted(snap["registers"].items())},
                     "summary": snap["summary"]},
        "prom": meta["prom"],
        "reference_check": rows,
    }
    with open(os.path.join(outdir, "capture.json"), "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write("\n")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Capture AD102/RTX 4090 cold-boot register state (read-only).")
    ap.add_argument("-d", "--device", help="PCI address, e.g. 0000:01:00.0")
    ap.add_argument("-o", "--out", help="output directory")
    ap.add_argument("--peek-dir", default=PEEK_DIR, help="gpu_peek module directory")
    ap.add_argument("--from-dmesg", help="parse a saved log instead of loading the module")
    ap.add_argument("--no-build", action="store_true", help="use an existing gpu_peek.ko")
    ap.add_argument("--no-rom", action="store_true", help="skip the VBIOS ROM dump")
    ap.add_argument("--allow-warm", action="store_true",
                    help="write output even if the read is not cold")
    args = ap.parse_args(argv)

    try:
        if args.from_dmesg:
            with open(args.from_dmesg) as f:
                log = f.read()
            bdf = args.device or "unknown"
        else:
            if os.geteuid() != 0:
                raise CaptureError("insmod needs root; re-run with sudo")
            bdf = args.device or find_ad102()
            driver = read_driver(bdf)
            if driver:
                raise CaptureError(
                    "%s is bound to '%s'; a cold read needs the NVIDIA driver "
                    "excluded for this boot (modprobe.blacklist=nvidia,...) and "
                    "a full power cycle." % (bdf, driver))
            ko = os.path.join(args.peek_dir, "gpu_peek.ko")
            if not args.no_build:
                ko = build_peek(args.peek_dir)
            elif not os.path.exists(ko):
                raise CaptureError("%s missing; drop --no-build" % ko)
            print("loading gpu_peek on %s ..." % bdf)
            log = run_peek(ko, bdf)

        snaps = parse_snapshots(log)
        if not snaps:
            raise CaptureError("no gpu_peek output found in the log")
        snap = select_cold_snapshot(snaps)
        prom = parse_prom(log)
        state, reasons = verdict(snap, prom)

        meta = {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "host": platform.node(),
            "kernel": platform.release(),
            "cmdline": read_text("/proc/cmdline") or "",
            "bdf": bdf,
            "identity": read_identity(bdf) if os.path.isdir(sysfs_path(bdf)) else {},
            "driver": read_driver(bdf) if os.path.isdir(sysfs_path(bdf)) else None,
            "resource0": read_resource0(bdf) if os.path.isdir(sysfs_path(bdf)) else None,
            "verdict": state,
            "verdict_reasons": reasons,
            "prom": {},
        }
        if not args.from_dmesg:
            try:
                meta["pci_config_dwords"] = read_config_space(bdf)
            except CaptureError as exc:
                meta["pci_config_dwords"] = None
                print("warning:", exc)
            if not args.no_rom:
                try:
                    data, digest = dump_rom(bdf)
                    if data:
                        meta["prom"]["bytes"] = len(data)
                        meta["prom"]["sha256"] = digest
                    if digest is None:
                        print("warning: ROM unreadable or signature is not 0xaa55")
                except CaptureError as exc:
                    print("warning:", exc)
        if prom.get("fwsec"):
            meta["prom"]["fwsec"] = prom["fwsec"]
        if prom.get("bytes_mapped"):
            meta["prom"]["mapped_bytes"] = prom["bytes_mapped"]

        rows = compare_reference(snap)

        outdir = args.out or os.path.join(
            REPO_DIR, "captures",
            "ad102-%s" % time.strftime("%Y%m%d-%H%M%S"))
        write_outputs(outdir, meta, snap, prom, log, rows)

        print("")
        print("verdict: %s" % state.upper())
        for reason in reasons:
            print("  - %s" % reason)
        print("")
        print("%-10s %-38s %-12s %-12s %s" %
              ("offset", "register", "expected", "captured", ""))
        for row in rows:
            got = "0x%08x" % row["actual"] if row["actual"] is not None else "-"
            mark = "" if row["match"] else ("MISMATCH" if row["match"] is False else "not sampled")
            print("%-10s %-38s 0x%08x   %-12s %s" %
                  ("0x%06x" % row["offset"], row["name"], row["expected"], got, mark))
        print("")
        print("wrote %s/{capture.json,registers.txt,profile.h,cold-entry.txt}" % outdir)

        if state != "cold" and not args.allow_warm:
            print("\nnot a cold read -- output kept for inspection but DO NOT use it "
                  "as a profile. Power off, wait ten seconds, boot without the "
                  "NVIDIA driver, then re-run.")
            return 2
        return 0
    except CaptureError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
