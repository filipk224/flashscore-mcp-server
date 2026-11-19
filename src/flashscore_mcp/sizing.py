"""Size the browser pool from the run's own memory and CPUs.

Any run size works (1 GB, 4 GB, 16 GB, 32 GB, 64 GB ...): the number of
browser pages open at once is

    pages = clamp(min(memory_pages, cpu_pages), 1, MAX_PAGES)
    memory_pages = floor((memory_mb - BASE_MB) / MB_PER_PAGE)
    cpu_pages    = max(2, floor(cpus * PAGES_PER_CPU))

Measured locally (Chromium headless shell from Playwright 1.64, images, fonts
and ads blocked, Flashscore results/standings/team pages): the idle browser
plus Python is about 400 MB; each open page adds about 390-500 MB RSS; one
page load costs about 6 CPU-seconds, about half a core over a 12 s load with
peaks near a full core (1, 4 and 8 pages at once used 0.6, 2.0 and 3.8 cores).
So MB_PER_PAGE is 512, BASE_MB 1024 (browser, Python, headroom), and
PAGES_PER_CPU 1. CPU is the limit long before memory. At least two pages are
allowed by CPU, since pages spend much of their time waiting on the network
(the old Apify setting was 2 pages on 2 GB). MAX_PAGES caps very large runs so
Flashscore is not hit with dozens of parallel loads.

Apify gives a run one CPU per 4 GB of memory, so 16 GB has 4 CPUs (4 pages)
and 64 GB has 16 CPUs (16 pages).

Inputs, in order: memory from ACTOR_MEMORY_MBYTES or APIFY_MEMORY_MBYTES (set
by Apify), else the cgroup memory limit, else the machine's MemTotal; CPUs from the cgroup
CPU quota, else memory / 4 GB when Apify gave the memory, else the OS CPU
count. An explicit FLASHSCORE_MAX_CONCURRENT_PAGES always wins.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import asdict, dataclass
from typing import Mapping, Optional

MB_PER_PAGE = 512
BASE_MB = 1024
PAGES_PER_CPU = 1.0
MIN_CPU_PAGES = 2
MAX_PAGES = 16
MB_PER_APIFY_CPU = 4096
DEFAULT_PAGES = 4  # nothing could be measured


@dataclass(frozen=True)
class Sizing:
    memory_mb: Optional[int]
    memory_source: str  # ACTOR_MEMORY_MBYTES, APIFY_MEMORY_MBYTES, cgroup, meminfo, unknown
    cpus: Optional[float]
    cpu_source: str  # cgroup, apify-memory, os, unknown
    memory_pages: Optional[int]
    cpu_pages: Optional[int]
    max_concurrent_pages: int
    pages_source: str  # computed, default, env
    mb_per_page: int = MB_PER_PAGE
    base_mb: int = BASE_MB
    pages_per_cpu: float = PAGES_PER_CPU
    max_pages: int = MAX_PAGES

    def as_dict(self) -> dict:
        return asdict(self)


def compute_pages(memory_mb: Optional[int], cpus: Optional[float]) -> tuple[int, Optional[int], Optional[int]]:
    """(pages, memory_pages, cpu_pages) for a machine. Pure."""
    memory_pages = max(0, (memory_mb - BASE_MB) // MB_PER_PAGE) if memory_mb else None
    cpu_pages = max(MIN_CPU_PAGES, math.floor(cpus * PAGES_PER_CPU)) if cpus else None
    limits = [p for p in (memory_pages, cpu_pages) if p is not None]
    if not limits:
        return DEFAULT_PAGES, None, None
    return max(1, min(MAX_PAGES, min(limits))), memory_pages, cpu_pages


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return None


def cgroup_memory_mb() -> Optional[int]:
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        raw = _read(path)
        if raw and raw.isdigit():
            value = int(raw)
            if value < 1 << 50:  # "unlimited" reads as a huge number
                return value // (1024 * 1024)
    return None


def cgroup_cpus() -> Optional[float]:
    raw = _read("/sys/fs/cgroup/cpu.max")
    if raw:
        quota, _, period = raw.partition(" ")
        if quota.isdigit() and period.isdigit() and int(period):
            return int(quota) / int(period)
    quota = _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and quota.isdigit() and period.isdigit() and int(quota) > 0 and int(period):
        return int(quota) / int(period)
    return None


def meminfo_mb() -> Optional[int]:
    raw = _read("/proc/meminfo") or ""
    found = re.search(r"^MemTotal:\s+(\d+) kB", raw, re.M)
    return int(found.group(1)) // 1024 if found else None


def detect(env: Mapping[str, str], cgroup_mem=cgroup_memory_mb, cgroup_cpu=cgroup_cpus, os_cpus=os.cpu_count, host_mem=meminfo_mb):
    """(memory_mb, memory_source, cpus, cpu_source) for this run."""
    memory_mb, memory_source = None, "unknown"
    for name in ("ACTOR_MEMORY_MBYTES", "APIFY_MEMORY_MBYTES"):
        raw = (env.get(name) or "").strip()
        if raw.isdigit() and int(raw) > 0:
            memory_mb, memory_source = int(raw), name
            break
    if memory_mb is None:
        memory_mb = cgroup_mem()
        if memory_mb:
            memory_source = "cgroup"
    if memory_mb is None:
        memory_mb = host_mem()
        if memory_mb:
            memory_source = "meminfo"
    cpus, cpu_source = cgroup_cpu(), "cgroup"
    if cpus is None and memory_source.endswith("MEMORY_MBYTES"):
        cpus, cpu_source = memory_mb / MB_PER_APIFY_CPU, "apify-memory"
    if cpus is None:
        count = os_cpus()
        cpus, cpu_source = (float(count), "os") if count else (None, "unknown")
    return memory_mb, memory_source, cpus, cpu_source


def size_for(env: Mapping[str, str], explicit_pages: Optional[int] = None, **detectors) -> Sizing:
    memory_mb, memory_source, cpus, cpu_source = detect(env, **detectors)
    pages, memory_pages, cpu_pages = compute_pages(memory_mb, cpus)
    source = "computed" if (memory_pages is not None or cpu_pages is not None) else "default"
    if explicit_pages:
        pages, source = explicit_pages, "env"
    return Sizing(
        memory_mb=memory_mb,
        memory_source=memory_source,
        cpus=round(cpus, 2) if cpus else cpus,
        cpu_source=cpu_source,
        memory_pages=memory_pages,
        cpu_pages=cpu_pages,
        max_concurrent_pages=pages,
        pages_source=source,
    )
