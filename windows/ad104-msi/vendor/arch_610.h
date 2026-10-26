/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GPU_UNLOCK_ARCH_610_H
#define GPU_UNLOCK_ARCH_610_H

enum gpu_unlock_booter_arch {
	GU_BOOTER_GA10X = 0,
	GU_BOOTER_AD10X = 1,
};

/* ---- Ada-series PCI device IDs ----
 * Every Ada card below uses the same AD102-family booter and V67 payload
 * (booter_load_ad102.bin + v67-ad102-610.43.03-four-plm.bin). "experimental"
 * marks cards that have not completed a cold-boot regression on this port. */

/* AD102 */
#define GU_AD102_RTX_4090          0x2684u   /* Linux-validated reference */
#define GU_AD102_RTX_4090_D        0x2685u   /* experimental */
#define GU_AD102_RTX_4070_TI_SUPER 0x2689u   /* experimental */

/* AD103 */
#define GU_AD103_RTX_4070_TI       0x2704u   /* experimental */
#define GU_AD103_RTX_4070_TI_SUPER 0x2705u   /* experimental */
#define GU_AD103_RTX_4070          0x2709u   /* experimental */
#define GU_AD103M_RTX_4090_MOBILE  0x2757u   /* experimental */

/* AD104 */
#define GU_AD104_RTX_4070_TI       0x2782u   /* Windows-validated reference */
#define GU_AD104_RTX_4070_SUPER    0x2783u   /* experimental */
#define GU_AD104_RTX_4070          0x2786u   /* experimental */

/* AD106 / AD107 */
#define GU_AD106_RTX_4060_TI       0x2803u   /* experimental */
#define GU_AD106_RTX_4060_TI_16GB  0x2805u   /* experimental */
#define GU_AD107_RTX_4060          0x2882u   /* experimental */
#define GU_AD107_RTX_4060_LAPTOP   0x28a0u   /* experimental */
#define GU_AD107_RTX_4060_MOBILE   0x28e0u   /* experimental */
#define GU_AD107_RTX_4050_MOBILE   0x28e1u   /* experimental */

/* Matches any Ada-series PCI device admitted by this port.
 * Widening this list does NOT weaken the per-card admission profile in
 * profile.c: PCI ID, subsystem, PROM hash, cold-entry register values and
 * the FWSEC geometry must still all match before any GPU register is written. */
static inline bool gpu_unlock_is_ada_pci(u32 device)
{
	switch (device) {
	case GU_AD102_RTX_4090:
	case GU_AD102_RTX_4090_D:
	case GU_AD102_RTX_4070_TI_SUPER:
	case GU_AD103_RTX_4070_TI:
	case GU_AD103_RTX_4070_TI_SUPER:
	case GU_AD103_RTX_4070:
	case GU_AD103M_RTX_4090_MOBILE:
	case GU_AD104_RTX_4070_TI:
	case GU_AD104_RTX_4070_SUPER:
	case GU_AD104_RTX_4070:
	case GU_AD106_RTX_4060_TI:
	case GU_AD106_RTX_4060_TI_16GB:
	case GU_AD107_RTX_4060:
	case GU_AD107_RTX_4060_LAPTOP:
	case GU_AD107_RTX_4060_MOBILE:
	case GU_AD107_RTX_4050_MOBILE:
		return true;
	default:
		return false;
	}
}

#endif /* GPU_UNLOCK_ARCH_610_H */
