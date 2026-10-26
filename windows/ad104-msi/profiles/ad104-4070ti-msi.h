/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * MSI RTX 4070 Ti (AD104, 10de:2782, subsystem 1462:5132).
 * The only profile that has completed end-to-end Windows validation
 * (Latence.app reference: MSI MPG Z490, i9-10850K, Win11 26200, driver 616.56).
 *
 * Still replace the TODO values with your own capture before flashing a
 * different board — the reference numbers below were read from one card.
 */
#ifndef PROFILE_AD104_4070TI_MSI_H
#define PROFILE_AD104_4070TI_MSI_H

#define PROFILE_PCI_VENDOR    0x10de
#define PROFILE_PCI_DEVICE    0x2782
#define PROFILE_PCI_SUBSYSTEM 0x51321462u

#define PROFILE_BAR0_BASE       0x00000004u
#define PROFILE_BAR0_SIZE_BYTES (16u * 1024u * 1024u)  /* 16 MiB */
#define PROFILE_PCI_COMMAND_EXPECTED 0x0003u

/* FWSEC geometry */
#define PROFILE_FWSEC_IMAGE_OFF      0x045488u
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

/* Cold-entry BAR0 values (AD104 reference) */
#define PROFILE_PMC_BOOT_0_REF      0x194000a1u   /* AD104 chip ID */
#define PROFILE_GFW_BOOT            0x00000000u
#define PROFILE_GFW_PLM             0x000003ffu
#define PROFILE_GFW_CPUCTL          0x00000010u
#define PROFILE_WPR_LO_EXPECTED     0x1ffffe00u
#define PROFILE_WPR_HI_EXPECTED     0x00000000u
#define PROFILE_WPR_CFG_PLM_COLD    0x0004cb8fu
#define PROFILE_FBPA_PLM_COLD       0xffffff0fu
#define PROFILE_WPR_PLM_COLD        0x0004cb8fu
#define PROFILE_FEAT_PLM_COLD       0xffffff8fu
#define PROFILE_FEAT_SS0_COLD       0x44023025u
#define PROFILE_FEAT_SS1_COLD       0x00000001u   /* AD104 cold SS1 = 1 */
#define PROFILE_FEAT_READOUT_COLD   0x00410080u

#define PROFILE_GFW_FALCON2_STATUS  0x00002ffau
#define PROFILE_GFM                 0x00000001u
#define PROFILE_WPR_CFG_PL0         0x0004cb8fu
#define PROFILE_WPR_LO_PL0          0x00100000u
#define PROFILE_WPR_HI_PL0          0x2ef9ff0u
#define PROFILE_FEAT_CLUSTER0       0x00000001u
#define PROFILE_FEAT_CLUSTER1       0x00000001u

#define PROFILE_PROM_SIZE (1024u * 1024u)
/* TODO: sha256 of the ROM dumped from your own 4070 Ti. */
#define PROFILE_PROM_HASH "0000000000000000000000000000000000000000000000000000000000000000"

/* Shared Ada firmware assets; pin the hashes of your generated files. */
#define PROFILE_ASSET_BOOTER       "AD104-ASSETS/booter_load_ad102.bin"
#define PROFILE_ASSET_BOOTER_SIZE  0u        /* TODO */
#define PROFILE_ASSET_BOOTER_HASH  "0000000000000000000000000000000000000000000000000000000000000000"
#define PROFILE_ASSET_PAYLOAD      "AD104-ASSETS/v67-ad102-610.43.03-four-plm.bin"
#define PROFILE_ASSET_PAYLOAD_SIZE 0u        /* TODO */
#define PROFILE_ASSET_PAYLOAD_HASH "0000000000000000000000000000000000000000000000000000000000000000"

#define PROFILE_SS0_UNLOCK 0x88888888u
#define PROFILE_SS1_UNLOCK 0x00000008u

#define PROFILE_EXPECTED_MARKER            0x67b00001u
#define PROFILE_EXPECTED_FEAT_PLM_OPEN     0xffffffffu
#define PROFILE_EXPECTED_WPR_PLM_OPEN      0xffffffffu
#define PROFILE_EXPECTED_FEAT_PLM_AFTER_FLR 0xffffffffu

#endif /* PROFILE_AD104_4070TI_MSI_H */
