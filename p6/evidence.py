"""Kernel evidence gates shared by load and recovery verification."""
import re


def kernel_anomalies(text):
    pattern = r'(?i)(\brcu\b.*\bstall\b|soft lockup|hard LOCKUP|\bBUG:|\bOops:|Kernel panic|No irq handler|unexpected IRQ|APIC error)'
    return [line for line in text.splitlines() if re.search(pattern, line)]


def hal_errors(serial, samples, observed=True):
    errors=[]
    if 'HAL probe matches=1 ' not in serial or 'HAL NoShorthand enforced=1 version=26100.1742' not in serial:
        errors.append('hal_boot_adaptation_missing')
    if observed and (not samples or any(row.get('hal_no_shorthand') != 1 for row in samples)):
        errors.append('hal_no_shorthand_not_retained')
    return errors
