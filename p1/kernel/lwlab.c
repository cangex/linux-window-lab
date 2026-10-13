// SPDX-License-Identifier: GPL-2.0-only
/* P1 single-AP experiment. No post-start reclaim: reboot the lab VM. */
#include <linux/cpu.h>
#include <linux/cpuhotplug.h>
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kexec.h>
#include <linux/kobject.h>
#include <linux/mutex.h>
#include <linux/sysfs.h>
#include <linux/sizes.h>
#include <linux/zdu.h>
#include <asm/apic.h>
#include "kexec_internal.h"

#define LW_MAGIC 0x313030765041574cULL
#define LW_BYTES SZ_16M
#define LW_ENTRY 0x10000
#define LW_STACK 0x100000
struct lw_handoff {
	u64 magic;
	u32 version, size;
	u64 generation;
	u32 cpu, apic_id;
	u64 base, bytes, entry, stack, cr3, mailbox, flags;
};
struct lw_mailbox {
	u64 generation;
	u32 apic_id, stage;
	u64 heartbeat, tsc, error, cr3, stack, magic;
};
extern int lwlab_kick_ap(unsigned int cpu, unsigned long entry, unsigned long handoff);
static DEFINE_MUTEX(lw_lock);
static const char *lw_state = "idle";
static int lw_error;
static phys_addr_t lw_base;
static void *lw_pool;
static struct lw_handoff *lw_h;
static struct lw_mailbox *lw_m;
static bool lw_started;
static unsigned int lw_cpu;

static void lw_transition(const char *state)
{
	pr_info("LWLAB: %s -> %s generation=%llu\n", lw_state, state, lw_h->generation);
	lw_state = state;
}

static ssize_t status_show(struct kobject *k, struct kobj_attribute *a, char *buf)
{
	ssize_t n;
	mutex_lock(&lw_lock);
	n = sysfs_emit(buf,
		"state=%s error=%d base=0x%llx bytes=0x%x cpu=%u expected_apic=%u generation=%llu "
		"ack_generation=%llu actual_apic=%u stage=%u heartbeat=%llu tsc=%llu "
		"payload_error=%llu cr3=0x%llx stack=0x%llx ack_magic=0x%llx started=%u\n",
		lw_state, lw_error, (u64)lw_base, LW_BYTES, lw_cpu, lw_h->apic_id, lw_h->generation,
		READ_ONCE(lw_m->generation), READ_ONCE(lw_m->apic_id), READ_ONCE(lw_m->stage),
		READ_ONCE(lw_m->heartbeat), READ_ONCE(lw_m->tsc), READ_ONCE(lw_m->error),
		READ_ONCE(lw_m->cr3), READ_ONCE(lw_m->stack), READ_ONCE(lw_m->magic), lw_started);
	mutex_unlock(&lw_lock);
	return n;
}

static int lw_prepare(const char *buf)
{
	unsigned int version, cpu;
	unsigned long long base, bytes, entry, generation, flags;
	const struct firmware *fw;
	u64 *pml4, *pdpt, *pd;
	int ret, end = 0, i;
	if (lw_started)
		return -EBUSY;
	if (sscanf(buf, "prepare %u %u %llx %llx %llx %llu %llu %n",
		   &version, &cpu, &base, &bytes, &entry, &generation, &flags, &end) != 7 ||
	    !end || buf[end])
		return -EINVAL;
	if (version != 1 || !generation || flags > 2)
		return -EINVAL;
	if (cpu == 0 || cpu >= nr_cpu_ids || !cpu_possible(cpu))
		return -EINVAL;
	if (cpu_online(cpu))
		return -EBUSY;
	if (base != lw_base || bytes != LW_BYTES || entry != lw_base + LW_ENTRY)
		return -ERANGE;
	ret = request_firmware(&fw, "lwlab/ap-probe.bin", NULL);
	if (ret)
		return ret;
	if (!fw->size || fw->size > SZ_64K) {
		release_firmware(fw);
		return -EFBIG;
	}
	memset(lw_h, 0, LW_BYTES);
	lw_cpu = cpu;
	*lw_h = (struct lw_handoff) {
		.magic = LW_MAGIC, .version = 1, .size = sizeof(*lw_h), .generation = generation,
		.cpu = cpu, .apic_id = apic->cpu_present_to_apicid(cpu),
		.base = base, .bytes = bytes, .entry = entry, .stack = base + LW_STACK,
		.cr3 = base + 0x2000, .mailbox = base + 0x1000, .flags = flags,
	};
	/* Private identity map: one 1-GiB window containing all P1 memory. */
	pml4 = (void *)lw_h + 0x2000;
	pdpt = (void *)lw_h + 0x3000;
	pd = (void *)lw_h + 0x4000;
	pml4[0] = (base + 0x3000) | 3;
	pdpt[(base >> 30) & 511] = (base + 0x4000) | 3;
	for (i = 0; i < 512; i++)
		pd[i] = (base & ~((1ULL << 30) - 1)) + ((u64)i << 21) + 0x83;
	lw_transition("prepared");
	memcpy((void *)lw_h + LW_ENTRY, fw->data, fw->size);
	release_firmware(fw);
	smp_wmb();
	lw_transition("loaded");
	return 0;
}

static int lw_start(void)
{
	unsigned long deadline;
	bool kicked = false;
	int ret;
	if (lw_started || strcmp(lw_state, "loaded"))
		return -EBUSY;
	if (cpu_online(lw_cpu))
		return -EBUSY;
	if (!kexec_trylock())
		return -EBUSY;
	/* Static P1 ownership: prevent Linux CPU re-online until VM reboot. */
	cpu_hotplug_disable();
	cpus_read_lock();
	if (cpu_online(lw_cpu)) {
		cpus_read_unlock();
		cpu_hotplug_enable();
		kexec_unlock();
		return -EBUSY;
	}
	lw_started = true;
	lw_transition("start-issued");
	ret = lwlab_kick_ap(lw_cpu, lw_h->entry, lw_base);
	cpus_read_unlock();
	if (ret)
		goto failed;
	kicked = true;
	deadline = jiffies + msecs_to_jiffies(3000);
	do {
		u32 stage = smp_load_acquire(&lw_m->stage);
		if (stage == 1 && !strcmp(lw_state, "start-issued"))
			lw_transition("payload-entered");
		if (stage == 255) {
			ret = -EIO;
			goto failed;
		}
		if (stage == 2 && READ_ONCE(lw_m->generation) == lw_h->generation &&
		    READ_ONCE(lw_m->apic_id) == lw_h->apic_id &&
		    READ_ONCE(lw_m->magic) == LW_MAGIC &&
		    READ_ONCE(lw_m->cr3) == lw_h->cr3 &&
		    READ_ONCE(lw_m->stack) == lw_h->stack && READ_ONCE(lw_m->heartbeat)) {
			if (!strcmp(lw_state, "start-issued"))
				lw_transition("payload-entered");
			lw_transition("payload-ready");
			ret = 0;
			goto out;
		}
		msleep(10);
	} while (time_before(jiffies, deadline));
	ret = -ETIMEDOUT;
failed:
	lw_transition("failed");
	/* Do not re-online the CPU or recycle memory after an uncertain start. */
out:
	/* Match the native AP bring-up cleanup while kexec remains serialized.
	 * do_zdu_boot_cpu already cleans up a failed IPI send itself.
	 */
	if (kicked) {
		arch_cpuhp_cleanup_kick_cpu(lw_cpu);
		pr_info("LWLAB: AP kick cleanup complete generation=%llu\n", lw_h->generation);
	}
	kexec_unlock();
	return ret;
}

static ssize_t control_store(struct kobject *k, struct kobj_attribute *a,
			     const char *buf, size_t count)
{
	int ret;
	mutex_lock(&lw_lock);
	if (sysfs_streq(buf, "start"))
		ret = lw_start();
	else if (!strncmp(buf, "prepare ", 8))
		ret = lw_prepare(buf);
	else
		ret = -EINVAL;
	lw_error = ret;
	mutex_unlock(&lw_lock);
	return ret ? ret : count;
}
static struct kobj_attribute status_attr = __ATTR_RO(status);
static struct kobj_attribute control_attr = __ATTR_WO(control);
static struct attribute *lw_attrs[] = { &status_attr.attr, &control_attr.attr, NULL };
static const struct attribute_group lw_group = { .attrs = lw_attrs };

static int __init lw_init(void)
{
	struct resource *r = zdu_pool_resource();
	struct kobject *k;
	BUILD_BUG_ON(sizeof(struct lw_handoff) != 88);
	BUILD_BUG_ON(sizeof(struct lw_mailbox) != 64);
	if (!r || resource_size(r) != LW_BYTES || !IS_ALIGNED(r->start, SZ_1G) ||
	    r->start >= (1ULL << 39))
		return -ENODEV;
	lw_pool = zdu_image_pool_create(LW_BYTES);
	if (!lw_pool)
		return -ENOMEM;
	lw_base = zdu_image_pool_alloc(lw_pool, LW_BYTES, PAGE_SIZE);
	if (!lw_base)
		return -ENOMEM;
	lw_h = phys_to_virt(lw_base);
	lw_m = (void *)lw_h + 0x1000;
	memset(lw_h, 0, LW_BYTES);
	k = kobject_create_and_add("lwlab", kernel_kobj);
	if (!k)
		return -ENOMEM;
	pr_info("LWLAB: reserved P1 region %pa bytes=0x%x\n", &lw_base, LW_BYTES);
	return sysfs_create_group(k, &lw_group);
}
late_initcall(lw_init);
