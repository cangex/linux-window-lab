# SPDX-License-Identifier: BSD-2-Clause-Patent
# Restricted DXE platform, derived from the UefiPayloadPkg library organization.
[Defines]
 PLATFORM_NAME = LwPartition
 PLATFORM_GUID = 55cbaad9-34f1-4e97-8abd-282fb331e952
 PLATFORM_VERSION = 0.1
 DSC_SPECIFICATION = 0x00010005
 OUTPUT_DIRECTORY = Build/LwPartition
 SUPPORTED_ARCHITECTURES = X64
 BUILD_TARGETS = DEBUG|RELEASE
 SKUID_IDENTIFIER = DEFAULT
 FLASH_DEFINITION = LwPartitionPkg/LwPartitionPkg.fdf
[SkuIds]
 0|DEFAULT
[BuildOptions]
 GCC:*_*_*_CC_FLAGS = -Wno-error=unused-parameter -Wno-error=missing-field-initializers
[BuildOptions.common.EDKII.DXE_RUNTIME_DRIVER]
 GCC:*_*_*_DLINK_FLAGS = -z common-page-size=0x1000
!include MdePkg/MdeLibs.dsc.inc
[LibraryClasses]
 DxeCoreEntryPoint|MdePkg/Library/DxeCoreEntryPoint/DxeCoreEntryPoint.inf
 UefiDriverEntryPoint|MdePkg/Library/UefiDriverEntryPoint/UefiDriverEntryPoint.inf
 UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf
 BaseLib|MdePkg/Library/BaseLib/BaseLib.inf
 BaseMemoryLib|MdePkg/Library/BaseMemoryLibRepStr/BaseMemoryLibRepStr.inf
 SynchronizationLib|MdePkg/Library/BaseSynchronizationLib/BaseSynchronizationLib.inf
 PrintLib|MdePkg/Library/BasePrintLib/BasePrintLib.inf
 CpuLib|MdePkg/Library/BaseCpuLib/BaseCpuLib.inf
 PciCf8Lib|MdePkg/Library/BasePciCf8Lib/BasePciCf8Lib.inf
 PciLib|MdePkg/Library/BasePciLibCf8/BasePciLibCf8.inf
 IoLib|MdePkg/Library/BaseIoLibIntrinsic/BaseIoLibIntrinsic.inf
 PeCoffLib|MdePkg/Library/BasePeCoffLib/BasePeCoffLib.inf
 PeCoffGetEntryPointLib|MdePkg/Library/BasePeCoffGetEntryPointLib/BasePeCoffGetEntryPointLib.inf
 CacheMaintenanceLib|MdePkg/Library/BaseCacheMaintenanceLib/BaseCacheMaintenanceLib.inf
 SafeIntLib|MdePkg/Library/BaseSafeIntLib/BaseSafeIntLib.inf
 PcdLib|MdePkg/Library/DxePcdLib/DxePcdLib.inf
 HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
 MemoryAllocationLib|MdePkg/Library/UefiMemoryAllocationLib/UefiMemoryAllocationLib.inf
 UefiBootServicesTableLib|MdePkg/Library/UefiBootServicesTableLib/UefiBootServicesTableLib.inf
 UefiRuntimeServicesTableLib|MdePkg/Library/UefiRuntimeServicesTableLib/UefiRuntimeServicesTableLib.inf
 UefiRuntimeLib|MdePkg/Library/UefiRuntimeLib/UefiRuntimeLib.inf
 UefiLib|MdePkg/Library/UefiLib/UefiLib.inf
 DevicePathLib|MdePkg/Library/UefiDevicePathLib/UefiDevicePathLib.inf
 UefiDecompressLib|MdePkg/Library/BaseUefiDecompressLib/BaseUefiDecompressLib.inf
 DxeServicesLib|MdePkg/Library/DxeServicesLib/DxeServicesLib.inf
 DxeServicesTableLib|MdePkg/Library/DxeServicesTableLib/DxeServicesTableLib.inf
 ExtractGuidedSectionLib|MdePkg/Library/DxeExtractGuidedSectionLib/DxeExtractGuidedSectionLib.inf
 DebugLib|MdePkg/Library/BaseDebugLibSerialPort/BaseDebugLibSerialPort.inf
 DebugPrintErrorLevelLib|MdePkg/Library/BaseDebugPrintErrorLevelLib/BaseDebugPrintErrorLevelLib.inf
 SerialPortLib|MdeModulePkg/Library/BaseSerialPortLib16550/BaseSerialPortLib16550.inf
 PlatformHookLib|MdeModulePkg/Library/BasePlatformHookLibNull/BasePlatformHookLibNull.inf
 DebugAgentLib|MdeModulePkg/Library/DebugAgentLibNull/DebugAgentLibNull.inf
 PeCoffExtraActionLib|MdePkg/Library/BasePeCoffExtraActionLibNull/BasePeCoffExtraActionLibNull.inf
 PerformanceLib|MdePkg/Library/BasePerformanceLibNull/BasePerformanceLibNull.inf
 ReportStatusCodeLib|MdePkg/Library/BaseReportStatusCodeLibNull/BaseReportStatusCodeLibNull.inf
 TimerLib|LwPartitionPkg/Library/LwTimerLib/LwTimerLib.inf
 CpuExceptionHandlerLib|UefiCpuPkg/Library/CpuExceptionHandlerLib/DxeCpuExceptionHandlerLib.inf
 UefiCpuBaseArchSupportLib|UefiCpuPkg/Library/BaseArchSupportLib/BaseArchSupportLib.inf
 LocalApicLib|UefiCpuPkg/Library/BaseXApicX2ApicLib/BaseXApicX2ApicLib.inf
 NestedInterruptTplLib|OvmfPkg/Library/NestedInterruptTplLib/NestedInterruptTplLib.inf
 CpuPageTableLib|UefiCpuPkg/Library/CpuPageTableLib/CpuPageTableLib.inf
 CcExitLib|UefiCpuPkg/Library/CcExitLibNull/CcExitLibNull.inf
 AmdSvsmLib|UefiCpuPkg/Library/AmdSvsmLibNull/AmdSvsmLibNull.inf
 ImagePropertiesRecordLib|MdeModulePkg/Library/ImagePropertiesRecordLib/ImagePropertiesRecordLib.inf
 SecurityManagementLib|MdeModulePkg/Library/DxeSecurityManagementLib/DxeSecurityManagementLib.inf
 CapsuleLib|MdeModulePkg/Library/DxeCapsuleLibNull/DxeCapsuleLibNull.inf
 AuthVariableLib|MdeModulePkg/Library/AuthVariableLibNull/AuthVariableLibNull.inf
 TpmMeasurementLib|MdeModulePkg/Library/TpmMeasurementLibNull/TpmMeasurementLibNull.inf
 VarCheckLib|MdeModulePkg/Library/VarCheckLib/VarCheckLib.inf
 VariablePolicyLib|MdeModulePkg/Library/VariablePolicyLib/VariablePolicyLib.inf
 VariablePolicyHelperLib|MdeModulePkg/Library/VariablePolicyHelperLib/VariablePolicyHelperLib.inf
 VariableFlashInfoLib|MdeModulePkg/Library/BaseVariableFlashInfoLib/BaseVariableFlashInfoLib.inf
[LibraryClasses.common.DXE_CORE]
 PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
 HobLib|MdePkg/Library/DxeCoreHobLib/DxeCoreHobLib.inf
 MemoryAllocationLib|MdeModulePkg/Library/DxeCoreMemoryAllocationLib/DxeCoreMemoryAllocationLib.inf
[LibraryClasses.common.DXE_RUNTIME_DRIVER]
 VariablePolicyLib|MdeModulePkg/Library/VariablePolicyLib/VariablePolicyLibRuntimeDxe.inf
[PcdsFixedAtBuild]
 gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x07
 gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0x8000004f
 gEfiMdeModulePkgTokenSpaceGuid.PcdSerialUseMmio|FALSE
 gEfiMdeModulePkgTokenSpaceGuid.PcdSerialRegisterBase|0x2f8
 gEfiMdeModulePkgTokenSpaceGuid.PcdSerialBaudRate|115200
 gEfiMdeModulePkgTokenSpaceGuid.PcdSerialUseHardwareFlowControl|FALSE
 gEfiMdeModulePkgTokenSpaceGuid.PcdSerialPciDeviceInfo|{0xff}
 gEfiMdeModulePkgTokenSpaceGuid.PcdDxeNxMemoryProtectionPolicy|0
 gEfiMdeModulePkgTokenSpaceGuid.PcdImageProtectionPolicy|0
 gEfiMdeModulePkgTokenSpaceGuid.PcdNullPointerDetectionPropertyMask|0
 gEfiMdeModulePkgTokenSpaceGuid.PcdCpuStackGuard|FALSE
 gEfiMdeModulePkgTokenSpaceGuid.PcdEmuVariableNvModeEnable|TRUE
 gEfiMdeModulePkgTokenSpaceGuid.PcdVariableStoreSize|0x10000
 gEfiMdeModulePkgTokenSpaceGuid.PcdMaxVariableSize|0x2000
 gEfiMdeModulePkgTokenSpaceGuid.PcdMaxHardwareErrorVariableSize|0x2000
[PcdsDynamicDefault]
 gEfiMdeModulePkgTokenSpaceGuid.PcdFlashNvStorageVariableBase|0
 gEfiMdeModulePkgTokenSpaceGuid.PcdFlashNvStorageVariableBase64|0
 gEfiMdeModulePkgTokenSpaceGuid.PcdEmuVariableNvStoreReserved|0
[Components]
 MdeModulePkg/Core/Dxe/DxeMain.inf
 MdeModulePkg/Universal/PCD/Dxe/Pcd.inf
 MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
 LwPartitionPkg/LwCpuDxe/LwCpuDxe.inf
 LwPartitionPkg/LwPlatformDxe/LwPlatformDxe.inf
 LwPartitionPkg/LwRuntimeDxe/LwRuntimeDxe.inf
 MdeModulePkg/Universal/Metronome/Metronome.inf
 MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf
 MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
 MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
 MdeModulePkg/Universal/MonotonicCounterRuntimeDxe/MonotonicCounterRuntimeDxe.inf
 MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
 MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf
 MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
 MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf
 FatPkg/EnhancedFatDxe/Fat.inf
 LwPartitionPkg/LwBdsDxe/LwBdsDxe.inf
 LwPartitionPkg/SelfTest/SelfTest.inf
 LwPartitionPkg/Child/Child.inf
