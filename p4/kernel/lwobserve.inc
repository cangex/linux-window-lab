/* SPDX-License-Identifier: GPL-2.0-only
 * Included inside lwlab.c: ownership and generation share the loader's lock.
 * No mmap/write operations and no access outside pre-reserved partition RAM.
 */
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/capability.h>
#include "lwobserve.h"
#define LWOBS_MAX_READ SZ_1M
static int lwobs_open(struct inode *inode, struct file *file)
{
 u64 *generation;
 if (!capable(CAP_SYS_RAWIO) || (file->f_mode & FMODE_WRITE)) return -EPERM;
 generation = kmalloc(sizeof(*generation), GFP_KERNEL);
 if (!generation) return -ENOMEM;
 mutex_lock(&lw_lock);
 if (!lw_started || READ_ONCE(lw_m->stage) != 3) {
  mutex_unlock(&lw_lock); kfree(generation); return -EAGAIN;
 }
 *generation = lw_h->generation;
 mutex_unlock(&lw_lock);
 file->private_data = generation;
 return 0;
}
static int lwobs_release(struct inode *inode, struct file *file)
{
 kfree(file->private_data); return 0;
}
static long lwobs_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
 struct lwobs_info info = { .version = 1, .count = 3, .max_read = LWOBS_MAX_READ,
  .extent = { {LW_BASE,LW_SIZE}, {LW_LOW_BASE,LW_LOW_SIZE}, {LW_REAL_BASE,LW_REAL_SIZE} } };
 void *maps[3] = {lw_h, lw_low, lw_real}, *source = NULL, *buffer;
 struct lwobs_read request;
 int i, result = 0;
 if (command != LWOBS_INFO && command != LWOBS_READ) return -ENOTTY;
 if (command == LWOBS_READ && copy_from_user(&request, (void __user *)arg, sizeof(request))) return -EFAULT;
 if (command == LWOBS_READ && (!request.length || request.length > LWOBS_MAX_READ)) return -EINVAL;
 mutex_lock(&lw_lock);
 info.generation = lw_h->generation;
 if (!lw_started || *(u64 *)file->private_data != info.generation || READ_ONCE(lw_m->stage) != 3) {
  result = -ESTALE; goto unlock;
 }
 if (command == LWOBS_INFO) {
  result = copy_to_user((void __user *)arg, &info, sizeof(info)) ? -EFAULT : 0;
  goto unlock;
 }
 if (request.generation != info.generation) { result = -ESTALE; goto unlock; }
 for (i=0; i<3; i++) {
  u64 base = info.extent[i].base, size = info.extent[i].bytes;
  if (request.address >= base && request.address-base < size &&
      request.length <= size-(request.address-base)) {
   source = maps[i] + (request.address-base); break;
  }
 }
 if (!source) { result = -ERANGE; goto unlock; }
 buffer = kvmalloc(request.length, GFP_KERNEL);
 if (!buffer) { result = -ENOMEM; goto unlock; }
 /* All maps share WB with Windows. Barriers order these loads; they do not
  * claim snapshot atomicity. Userspace must validate the writer protocol. */
 smp_rmb(); memcpy(buffer, source, request.length); smp_rmb();
 if (copy_to_user(u64_to_user_ptr(request.buffer), buffer, request.length)) result = -EFAULT;
 kvfree(buffer);
unlock:
 mutex_unlock(&lw_lock); return result;
}
static const struct file_operations lwobs_fops = {
 .owner = THIS_MODULE, .open = lwobs_open, .release = lwobs_release,
 .unlocked_ioctl = lwobs_ioctl, .compat_ioctl = lwobs_ioctl,
};
static struct miscdevice lwobs_device = {
 .minor = MISC_DYNAMIC_MINOR, .name = "lwobserve", .fops = &lwobs_fops, .mode = 0600,
};
