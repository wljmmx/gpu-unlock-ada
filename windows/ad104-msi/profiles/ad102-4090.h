/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * RTX 4090 (AD102, 10de:2684) — hardware profile TEMPLATE.
 *
 * Everything marked TODO MUST be captured from YOUR card before use. The
 * reference values below come from the Linux cold-boot validation run of
 * gpu-unlock-ada; they are a starting point, not a licence to skip capture.
 * Different AIBs, VBIOS versions and motherboards differ in subsystem ID,
 * PROM hash and several cold-entry register words.
 */
#ifndef PROFILE_AD102_4090_H
#define PROFILE_AD102_4090_H

#define PROFILE_PCI_VENDOR   0x10de
#define PROFILE_PCI_DEVICE   0x2684   /* RTX 4090; 0x2685 for 4090 D */
#define PROFILE_PCI_SUBSYSTEM 0x00000000  /* TODO: lspci -vv | grep Subsystem */

/* BAR0 aperture as assigned by this board's firmware. 0x80000000 is what the
 * MSI 4070 Ti reference saw; a 4090 boot may assign something else, so capture
 * your own value instead of assuming. */
#define PROFILE_BAR0_BASE       0x80000000ULL   /* TODO: verify on your board */
#define PROFILE_BAR0_SIZE_BYTES 0x01000000u     /* TODO: verify (16 MiB assumed) */
#define PROFILE_PCI_COMMAND_EXPECTED 0x0003u

/* ---- FWSEC geometry ----
 * Mirrors the AD104 pins; the AD102 report only states the DMEM length
 * (0xd80). Confirm every field by parsing your own ROM:
 *   sudo ./tools/capture_ad102_cold.py            (prints the parsed line and
 *                                                  writes a filled profile)
 * or windows/ad104-msi/tools/fwsec_inspect.c against your dump. */
#define PROFILE_FWSEC_IMAGE_OFF      0x045488u   /* TODO: confirm on your VBIOS */
#define PROFILE_FWSEC_IMAGE_SIZE     0x010300u
#define PROFILE_FWSEC_IMEM_PA        0x00000000u
#define PROFILE_FWSEC_IMEM_SIZE      0x00f500u
#define PROFILE_FWSEC_IMEM_VA        0x00000000u
#define PROFILE_FWSEC_DMEM_PA        0x00000000u
#define PROFILE_FWSEC_DATA_OFF       0x00f500u
#define PROFILE_FWSEC_DMEM_SIZE      0x000d80u
#define PROFILE_FWSEC_PKC_OFF        0x00000b24u
#define PROFILE_FWSEC_INTERFACE_OFF  0x0000001cu
#define PROFILE_FWSEC_UCODE_ID       9u
#define PROFILE_FWSEC_ENGINE_MASK    0x0400u
#define PROFILE_FWSEC_SIG_COUNT      2u
#define PROFILE_FWSEC_SIG_VERSIONS   3u
#define PROFILE_FWSEC_SIG_OFF        0x045188u
#define PROFILE_FWSEC_SIG_BYTES      768u

/* ---- Cold-entry BAR0 values ----
 * The published AD102 cold words are pinned below. GFW_PLM / GFW_BOOT /
 * GFW_CPUCTL are marked TODO: the 4090 evidence only exposes them through the
 * gpu_peek summary predicates (gfw_plm_level0=1, boot_completed=1,
 * falcon_halted=1), not as literal words.
 *
 * NOTE: windows/ad104-msi/profile.c Registers() carries the authoritative
 * 19-word admission table as static arrays; this header alone is not enough
 * for a new board. tools/capture_ad102_cold.py emits the arrays from your own
 * capture as cold-entry.txt. */
#define PROFILE_PMC_BOOT_0_REF      0x192000a1u   /* AD102 chip ID */
#define PROFILE_GFW_BOOT            0x00000000u   /* TODO: capture literal */
#define PROFILE_GFW_PLM             0x000003ffu   /* TODO: capture literal */
#define PROFILE_GFW_CPUCTL          0x00000010u   /* TODO: capture literal */
#define PROFILE_WPR_LO_EXPECTED     0x1ffffe00u
#define PROFILE_WPR_HI_EXPECTED     0x00000000u
#define PROFILE_WPR_CFG_PLM_COLD    0x0004cb8fu
#define PROFILE_FBPA_PLM_COLD       0xffffff0fu
#define PROFILE_WPR_PLM_COLD        0x0004cb8fu
#define PROFILE_FEAT_PLM_COLD       0xffffff8fu
#define PROFILE_FEAT_SS0_COLD       0x44023025u
#define PROFILE_FEAT_SS1_COLD       0x00000007u   /* AD102 cold SS1 = 7 */
#define PROFILE_FEAT_READOUT_COLD   0x00410080u

#define PROFILE_GFW_FALCON2_STATUS  0x00002ffau
#define PROFILE_GFM                 0x00000001u
#define PROFILE_WPR_CFG_PL0         0x0004cb8fu
#define PROFILE_WPR_LO_PL0          0x00100000u
#define PROFILE_WPR_HI_PL0          0x2ef9ff0u
#define PROFILE_FEAT_CLUSTER0       0x00000001u
#define PROFILE_FEAT_CLUSTER1       0x00000001u

/* ---- PROM / VBIOS ---- */
#define PROFILE_PROM_SIZE (1024u * 1024u)  /* verify rom_size on your board */
/* TODO: sha256sum of the ROM you dumped from YOUR card (64 lowercase hex). */
#define PROFILE_PROM_HASH "0000000000000000000000000000000000000000000000000000000000000000"

/* ---- Firmware assets (shared by every Ada card; integrity-pinned) ----
 * Generate with firmware/generate_v67.py and extract_boot_assets.py, then
 * pin the SHA-256 of each file you produced. Sizes below are the upstream
 * reference sizes. */
#define PROFILE_ASSET_BOOTER       "AD102-ASSETS/booter_load_ad102.bin"
#define PROFILE_ASSET_BOOTER_SIZE  0u        /* TODO: actual size */
#define PROFILE_ASSET_BOOTER_HASH  "0000000000000000000000000000000000000000000000000000000000000000"

#define PROFILE_ASSET_PAYLOAD      "AD102-ASSETS/v67-ad102-610.43.03-four-plm.bin"
#define PROFILE_ASSET_PAYLOAD_SIZE 0u        /* TODO */
#define PROFILE_ASSET_PAYLOAD_HASH "0000000000000000000000000000000000000000000000000000000000000000"

/* ---- Speed selector unlock values (same across Ada) ---- */
#define PROFILE_SS0_UNLOCK 0x88888888u
#define PROFILE_SS1_UNLOCK 0x00000008u

#define PROFILE_EXPECTED_MARKER            0x67b00001u
#define PROFILE_EXPECTED_FEAT_PLM_OPEN     0xffffffffu
#define PROFILE_EXPECTED_WPR_PLM_OPEN      0xffffffffu
#define PROFILE_EXPECTED_FEAT_PLM_AFTER_FLR 0xffffffffu

#endif /* PROFILE_AD102_4090_H */
