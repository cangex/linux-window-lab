/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef LW_OBSERVE_H
#define LW_OBSERVE_H
#include <linux/types.h>
#include <linux/ioctl.h>
struct lwobs_extent { __u64 base, bytes; };
struct lwobs_info { __u64 version, generation, count, max_read; struct lwobs_extent extent[3]; };
struct lwobs_read { __u64 generation, address, length, buffer; };
#define LWOBS_INFO _IOR('W', 0x40, struct lwobs_info)
#define LWOBS_READ _IOW('W', 0x41, struct lwobs_read)
#endif
