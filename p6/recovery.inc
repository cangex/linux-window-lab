/* SPDX-License-Identifier: GPL-2.0-only
 * Fixed-Q35 experimental stop. Failure retains all ownership. No RAM reclaim.
 */
static bool lw_hotplug_held;
static u64 lw_stop_nonce;
static u32 lw_stop_ipi(u32 command, u32 target)
{
 unsigned long flags;
 u32 error;
 /* xAPIC ICR high/low writes must not interleave with a local IRQ's IPI. */
 local_irq_save(flags);
 error = safe_apic_wait_icr_idle();
 if (!error) {
  apic_icr_write(command, target);
  error = safe_apic_wait_icr_idle();
 }
 local_irq_restore(flags);
 return error;
}
static int lw_stop_partition(void)
{
 struct pci_dev *dev;
 void __iomem *bar = NULL;
 unsigned long deadline;
 u64 *ack = (void *)lw_h + 0xe00;
 int cpu, j, ret = -EIO, cap;
 u32 cc, value, low, high;
 u16 control;
 if (!lw_started)
  return -EINVAL;
 for (cpu = 4; cpu < 8; cpu++)
  if (!cpu_possible(cpu) || cpu_online(cpu) || apic->cpu_present_to_apicid(cpu) != cpu)
   return -EBUSY;
 dev = pci_get_domain_bus_and_slot(0,129,PCI_DEVFN(0,0));
 if (!dev || !dev->driver || strcmp(dev->driver->name,"pci-stub")) {
  if (dev) pci_dev_put(dev);
  return -ENODEV;
 }
 pci_read_config_dword(dev,PCI_BASE_ADDRESS_0,&low);
 pci_read_config_dword(dev,PCI_BASE_ADDRESS_1,&high);
 if (high || (low & PCI_BASE_ADDRESS_MEM_MASK) != P5_NVME_BAR) goto out;
 bar = ioremap(P5_NVME_BAR,P5_NVME_SIZE);
 if (!bar) { ret=-ENOMEM; goto out; }
 /* Existing readers share lw_lock. Revoke reads before changing CPU/device state. */
 lw_transition("quiescing");
 WRITE_ONCE(lw_m->stage,4);
 lw_stop_nonce = ktime_get_ns() | (1ULL<<63);
 for (cpu=4;cpu<8;cpu++) WRITE_ONCE(ack[cpu],0);
 WRITE_ONCE(*(u64 *)((void *)lw_h+0xe80),lw_stop_nonce);
 smp_wmb();
 /* Targeted physical destinations only. The parking page is never cleared. */
 for (cpu=4;cpu<8;cpu++) {
  preempt_disable();
  value=lw_stop_ipi(APIC_INT_LEVELTRIG|APIC_INT_ASSERT|APIC_DM_INIT,cpu);
  udelay(10000);
  value|=lw_stop_ipi(APIC_INT_LEVELTRIG|APIC_DM_INIT,cpu);
  for(j=0;j<2;j++) {
   value|=lw_stop_ipi(APIC_DM_STARTUP|0x6f,cpu); udelay(300);
  }
  preempt_enable();
  if(value)goto failed;
 }
 deadline=jiffies+msecs_to_jiffies(2000);
 for(;;) {
  bool all=true;
  for(cpu=4;cpu<8;cpu++) if(smp_load_acquire(&ack[cpu])!=lw_stop_nonce)all=false;
  if(all)break;
  if(time_after_eq(jiffies,deadline)){ret=-ETIMEDOUT;goto failed;}
  msleep(1);
 }
 /* CPU acknowledgement is insufficient: quiesce the owned NVMe separately. */
 cap=pci_find_capability(dev,PCI_CAP_ID_MSIX);
 if(cap) {pci_read_config_word(dev,cap+PCI_MSIX_FLAGS,&control);pci_write_config_word(dev,cap+PCI_MSIX_FLAGS,control|PCI_MSIX_FLAGS_MASKALL);}
 writel(~0U,bar+0xc);
 cc=readl(bar+0x14);writel(cc&~1U,bar+0x14);
 deadline=jiffies+msecs_to_jiffies(10000);
 while((value=readl(bar+0x1c))&1) {
  if(time_after_eq(jiffies,deadline)){ret=-ETIMEDOUT;goto failed;}
  msleep(1);
 }
 if(value==~0U)goto failed;
 pci_clear_master(dev);
 if(!pci_wait_for_pending_transaction(dev))goto failed;
 ret=pci_reset_function(dev);
 if(ret)goto failed;
 pci_clear_master(dev);
 lw_started=false;
 lw_transition("stopped");
 pr_info("LWLAB P6: four parked CPUs and NVMe reset; nonce=%llu generation=%llu\n",lw_stop_nonce,lw_h->generation);
 ret=0;goto out;
failed:
 /* Block prepare even after partial success; never infer that timeout is idle. */
 lw_transition("failed-retained");
out:
 if(bar)iounmap(bar);
 pci_dev_put(dev);
 return ret;
}
