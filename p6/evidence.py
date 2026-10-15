"""Kernel evidence gates shared by load and recovery verification."""
import re


def kernel_anomalies(text):
    pattern = r'(?i)(\brcu\b.*\bstall\b|soft lockup|hard LOCKUP|\bBUG:|\bOops:|Kernel panic|No irq handler|unexpected IRQ|APIC error)'
    return [line for line in text.splitlines() if re.search(pattern, line)]
