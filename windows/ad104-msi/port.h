/* Modified 2026-10-19/20 for Windows GPU UNLOCK; changes documented in CHANGES.md. */ #pragma once
#include <Uefi.h>
#include <Protocol/PciIo.h>
#include <Protocol/DevicePath.h>
#include <stddef.h>

/* ---- Hardware-profile selection ----
 * Select a profile at compile time:
 *   -DGPU_PROFILE_AD102_RTX4090        RTX 4090        10de:2684
 *   -DGPU_PROFILE_AD103_RTX4070TIS     RTX 4070 Ti S   10de:2705
 *   -DGPU_PROFILE_AD104_RTX4070TI_MSI  RTX 4070 Ti     10de:2782  (default)
 * or manual:
 *   -DGPU_PROFILE_PCI_DEVICE=0x2684 -DGPU_PROFILE_SUBSYSTEM=0xXXXXXXXX
 *
 * A profile only decides which card family the admission checks expect; it
 * never disables them. Every new board still needs its own captured profile
 * (see profiles/*.h and docs/PORTING-GUIDE.md). */
#if   defined(GPU_PROFILE_AD102_RTX4090)
#define GPU_PROFILE_PCI_VENDOR   0x10deU
#define GPU_PROFILE_PCI_DEVICE   0x2684U
#define GPU_PROFILE_SUBSYSTEM    0x00000000U  /* TODO: capture your subsystem */
#define GPU_PROFILE_BAR0_BASE    0x00000004U
#elif defined(GPU_PROFILE_AD103_RTX4070TIS)
#define GPU_PROFILE_PCI_VENDOR   0x10deU
#define GPU_PROFILE_PCI_DEVICE   0x2705U
#define GPU_PROFILE_SUBSYSTEM    0x00000000U  /* TODO: capture your subsystem */
#define GPU_PROFILE_BAR0_BASE    0x00000004U
#elif defined(GPU_PROFILE_AD104_RTX4070TI_MSI)
#define GPU_PROFILE_PCI_VENDOR   0x10deU
#define GPU_PROFILE_PCI_DEVICE   0x2782U
#define GPU_PROFILE_SUBSYSTEM    0x51321462U
#define GPU_PROFILE_BAR0_BASE    0x00000004U
#else
/* Default: the only end-to-end validated Windows profile. */
#define GPU_PROFILE_AD104_RTX4070TI_MSI 1
#define GPU_PROFILE_PCI_VENDOR   0x10deU
#define GPU_PROFILE_PCI_DEVICE   0x2782U
#define GPU_PROFILE_SUBSYSTEM    0x51321462U
#define GPU_PROFILE_BAR0_BASE    0x00000004U
#endif

/* Manual override / fallback */
#ifdef GPU_PROFILE_PCI_DEVICE
#undef  GU_BOARD_ID
#define GU_BOARD_ID   (((UINT32)GPU_PROFILE_PCI_DEVICE << 16) | (UINT32)GPU_PROFILE_PCI_VENDOR)
#endif
#ifdef GPU_PROFILE_SUBSYSTEM
#undef  GU_BOARD_SUBSYSTEM
#define GU_BOARD_SUBSYSTEM (UINT32)GPU_PROFILE_SUBSYSTEM
#endif
#ifndef GU_BOARD_ID
#define GU_BOARD_ID   (((UINT32)GPU_PROFILE_PCI_DEVICE << 16) | (UINT32)GPU_PROFILE_PCI_VENDOR)
#endif
#ifndef GU_BOARD_SUBSYSTEM
#define GU_BOARD_SUBSYSTEM (UINT32)GPU_PROFILE_SUBSYSTEM
#endif
#ifndef GU_BAR0_BASE
#define GU_BAR0_BASE  0x80000000ULL
#endif
#ifndef GU_DEVICE_MEMORY_SIZE
#define GU_DEVICE_MEMORY_SIZE 0x2ffaU
#endif
/* The default artifact is read-only. Legacy host containment tests are never
   a production enable switch; experimental firmware requires its own define. */
#if defined(GU_AD104_HOST_TEST) && __STDC_HOSTED__ != 1
#error GU_AD104_HOST_TEST is forbidden in firmware builds
#endif
#if defined(GU_STOCK_PROFILE_SS0) || defined(GU_STOCK_PROFILE_NAME)
#error Stock profile value and name must be derived from the explicit selector
#endif
#if (defined(GU_STOCK_PROFILE_ORIGINAL_03100062) + defined(GU_STOCK_PROFILE_OBSERVED_03000062) + defined(GU_ENTRY_LATCHED_SS1_PRESERVE) + defined(GU_ENTRY_LATCHED_SS1_FULL)) > 1
#error Select exactly one stock profile
#endif
#if defined(GU_AD104_TRANSACTION) && defined(GU_STOCK_PROFILE_ORIGINAL_03100062)
#define GU_STOCK_PROFILE_SS0 0x03100062U
#define GU_STOCK_PROFILE_NAME "original03100062"
#elif defined(GU_AD104_TRANSACTION) && defined(GU_STOCK_PROFILE_OBSERVED_03000062)
#define GU_STOCK_PROFILE_SS0 0x03000062U
#define GU_STOCK_PROFILE_NAME "observed03000062"
#elif defined(GU_AD104_TRANSACTION) && defined(GU_ENTRY_LATCHED_SS1_PRESERVE)
#define GU_STOCK_PROFILE_NAME "entryLatchedSs1Preserve"
#elif defined(GU_AD104_TRANSACTION) && defined(GU_ENTRY_LATCHED_SS1_FULL)
#define GU_STOCK_PROFILE_NAME "entryLatchedSs1Full"
#elif defined(GU_AD104_TRANSACTION)
#error Experimental firmware requires exactly one explicit stock profile
#elif defined(GU_STOCK_PROFILE_ORIGINAL_03100062) || defined(GU_STOCK_PROFILE_OBSERVED_03000062) || defined(GU_ENTRY_LATCHED_SS1_PRESERVE) || defined(GU_ENTRY_LATCHED_SS1_FULL)
#error Stock profile selection requires experimental firmware
#endif
#if defined(GU_AD104_TRANSACTION) || (defined(GU_AD104_HOST_TEST) && __STDC_HOSTED__ == 1)
#define GU_PREFLIGHT_ONLY 0
#else
#define GU_PREFLIGHT_ONLY 1
#endif
#if defined(GU_ENTRY_LATCHED_SS1_PRESERVE) || defined(GU_ENTRY_LATCHED_SS1_FULL)
#define GU_ENTRY_LATCHED 1
#endif
#define GU_SELECTOR_PHASE_ENTRY 0U
#define GU_SELECTOR_PHASE_SS0_WRITTEN 1U
#define GU_SELECTOR_PHASE_SS1_WRITE 2U
#define GU_SELECTOR_PHASE_TARGET 3U
typedef struct GU_DMA GU_DMA;
struct GU_DMA {
  GU_DMA *next;
  VOID *cpu, *mapping;
  UINT64 dma;
  UINTN bytes, pages;
  BOOLEAN mapped;
};
typedef struct {
  EFI_BOOT_SERVICES *bs;
  EFI_PCI_IO_PROTOCOL *pci;
  EFI_HANDLE image, handle;
  UINT64 bar_base, bar_size, ticks;
  UINT16 pm_cap, pcie_cap, msi_cap, msix_cap;
  UINT32 saved_config[64];
  UINT16 saved_devctl, saved_devctl2;
  UINT8 pcie_version;
  BOOLEAN fault, retained, started, quiesced, armed, owned, display_ok, saved;
  BOOLEAN profile_verified, prom_verified;
  BOOLEAN transaction_attempted;
  BOOLEAN master_attributes_pending;
  UINT64 master_original_attributes;
  UINT16 master_original_command;
  EFI_PCI_IO_PROTOCOL *master_pci;
  /* Containment may run at TPL_NOTIFY. Capture diagnostics without file IO;
     preserve first errors even if a later containment retry succeeds. */
  EFI_STATUS master_attribute_status, master_hardware_status;
  UINT64 master_last_attributes;
  UINT16 master_last_command;
  UINT32 flrs, mmio_writes, dma_count;
  GU_DMA *allocations;
  BOOLEAN (*display_check)(VOID);
} GU_PLATFORM;
extern GU_PLATFORM Gu;

VOID GuInit(EFI_BOOT_SERVICES *Bs, EFI_PCI_IO_PROTOCOL *Pci);
#ifdef GU_ENTRY_LATCHED
/* Only ColdCheck may latch, after all exact-card/cold/PROM checks. These
   values are private to port.c; the vendor core can only read/compare them. */
BOOLEAN GuLatchEntrySelectors(UINT32 Ss0, UINT32 Ss1);
BOOLEAN GuGetEntrySelectors(UINT32 *Ss0, UINT32 *Ss1);
BOOLEAN GuEntrySelectorsMatch(UINT32 Ss0, UINT32 Ss1);
#endif
#ifdef GU_ENTRY_LATCHED_SS1_FULL
/* The full policy owns the only permitted SS1 write phase. */
BOOLEAN GuSelectorPhase(UINT32 Phase);
#endif
BOOLEAN GuTargetConfig(const UINT32 *Config, UINTN Segment, UINTN Bus, UINTN Device, UINTN Function);
BOOLEAN GuSafeToReturn(VOID);
EFI_STATUS GuDmaAllocate(UINTN Bytes, VOID **Cpu, UINT64 *Dma);
EFI_STATUS GuDmaFree(VOID *Cpu, UINT64 Dma);
UINT32 GuRead32(UINT32 Offset);
VOID GuWrite32(UINT32 Offset, UINT32 Value);
EFI_STATUS GuSavePci(VOID);
EFI_STATUS GuRestorePci(VOID);
EFI_STATUS GuFlr(VOID);
EFI_STATUS GuClearMaster(VOID);
EFI_STATUS GuEnableMaster(VOID);
EFI_STATUS GuConfigRead(EFI_PCI_IO_PROTOCOL_WIDTH Width, UINT32 Offset, VOID *Value);
EFI_STATUS GuConfigWrite(EFI_PCI_IO_PROTOCOL_WIDTH Width, UINT32 Offset, VOID *Value);
VOID GuStarted(VOID);
VOID GuQuiesced(VOID);
VOID GuLog(const char *Format, ...);
VOID GuLogText(const char *Text);
VOID GuCopyFromIo(VOID *Destination, const VOID *Source, size_t Bytes);
VOID *GuAlloc(size_t Bytes);
VOID GuFree(VOID *Memory);
VOID GuStall(UINTN Microseconds);
