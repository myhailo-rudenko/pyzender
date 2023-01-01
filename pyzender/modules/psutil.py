import psutil

from pyzender.modules.base import Module, Data, Discovery


class PSUtil(Module):
    def _collect_data_reports(self):
        self._cpu()
        self._memory()

    def _collect_discovery_reports(self):
        self._discover_threads()

    def _discover_threads(self):
        threads = [n for n in range(psutil.cpu_count())]
        discovery = Discovery(
            key="psutil.thread.discovery", macros="{#THREAD}",
            values=threads
        )
        self._report(discovery)

    def _per_cpu_usage(self):
        per_cpu_usage = psutil.cpu_percent(percpu=True)

        for index, usage in enumerate(per_cpu_usage):
            data = Data(
                items={"usage": usage},
                key="psutil.cpu",
                append_key=f"[{index}]",
                timestamp=self.timestamp(),
            )
            self._report(data)

    def _per_cpu_frequency(self):
        per_cpu_frequency = psutil.cpu_freq(percpu=True)

        for index, frequency in enumerate(per_cpu_frequency):
            data = Data(
                items={
                    "current": frequency.current,
                    "min": frequency.min,
                    "max": frequency.max,
                },
                key="psutil.cpu.frequency",
                append_key=f"[{index}]",
                timestamp=self.timestamp(),
            )
            self._report(data)

    def _cpu_general(self):
        cores = psutil.cpu_count(logical=False)
        threads = psutil.cpu_count()
        loadavg_1_min, loadavg_5_min, loadavg_15_min = psutil.getloadavg()
        stats = psutil.cpu_stats()
        usage = psutil.cpu_percent()
        frequency = psutil.cpu_freq()
        cpu_times = psutil.cpu_times_percent()

        data = Data(
            items={
                "cores": cores,
                "threads": threads,
                "loadavg": {"1min": loadavg_1_min, "5min": loadavg_5_min, "15min": loadavg_15_min},
                "ctx_switches": stats.ctx_switches,
                "interrupts": stats.interrupts,
                "soft_interrupts": stats.soft_interrupts,
                "sys_calls": stats.syscalls,
                "usage": usage,
                "frequency": {
                    "current": frequency.current,
                    "min": frequency.min,
                    "max": frequency.max,
                },
                "times": {
                    "user": cpu_times.user,
                    "nice": cpu_times.nice,
                    "system": cpu_times.system,
                    "idle": cpu_times.idle,
                    "iowait": cpu_times.iowait,
                    "irq": cpu_times.irq,
                    "softirq": cpu_times.softirq,
                    "steal": cpu_times.steal,
                    "guest": cpu_times.guest,
                    "guest_nice": cpu_times.guest_nice,
                },
            },
            key="psutil.cpu",
            timestamp=self.timestamp(),
        )
        self._report(data)

    def _cpu(self):
        self._cpu_general()
        self._per_cpu_usage()
        self._per_cpu_frequency()

    def _memory(self):
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        data = Data(
            items={
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                    "free": memory.free,
                    "active": memory.active,
                    "inactive": memory.inactive,
                    "buffers": memory.buffers,
                    "cached": memory.cached,
                    "shared": memory.shared,
                },
                "swap": {
                    "total": swap.total,
                    "used": swap.used,
                    "free": swap.free,
                    "percent": swap.percent,
                    "swapped_in": swap.sin,
                    "swapped_out": swap.sout,
                },
            },
            key="psutil",
            timestamp=self.timestamp(),
        )
        self._report(data)
