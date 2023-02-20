import psutil

from pyzender.modules.base import Module, Data, Discovery

IP4_ADDRESS_FAMILY = 2
IP6_ADDRESS_FAMILY = 10


class PSUtil(Module):
    @staticmethod
    def _is_disk_useful(disk: str) -> bool:
        return not any([("loop" in disk), ("dm" in disk)])

    @staticmethod
    def _get_useful_partitions() -> list:
        disk_partitions = psutil.disk_partitions(all=False)
        excluded_fstypes = ["squashfs"]
        return [p for p in disk_partitions if p.fstype not in excluded_fstypes]

    def _collect_data_reports(self):
        self._cpu()
        self._memory()
        self._disks()
        self._mountpoints()
        self._temperature_sensors()
        self._networks()

    def _collect_discovery_reports(self):
        self._discover_threads()
        self._discover_disks()
        self._discover_mountpoints()
        self._discover_temperature_sensors()
        self._discover_network_interfaces()

    def _discover_network_interfaces(self):
        nics = [nic for nic in psutil.net_if_addrs()]
        discovery = Discovery(key="psutil.net.discovery", macros="{#NIC}", values=nics)
        self._report(discovery)

    def _discover_threads(self):
        threads = [n for n in range(psutil.cpu_count())]

        discovery = Discovery(
            key="psutil.thread.discovery", macros="{#THREAD}",
            values=threads
        )

        self._report(discovery)

    def _discover_mountpoints(self):
        mount_points = [p.mountpoint for p in self._get_useful_partitions()]

        discovery = Discovery(
            key="psutil.mountpoint.discovery", macros="{#MOUNTPOINT}",
            values=mount_points
        )

        self._report(discovery)

    def _discover_disks(self):
        per_disk_counters = psutil.disk_io_counters(perdisk=True, nowrap=False)
        disks = [d for d, _ in per_disk_counters.items() if self._is_disk_useful(d)]

        discovery = Discovery(
            key="psutil.disk.discovery", macros="{#DISK}",
            values=disks
        )

        self._report(discovery)

    def _discover_temperature_sensors(self):
        temperature_sensors = psutil.sensors_temperatures()

        sensors = []
        for sensor, readings in temperature_sensors.items():
            for reading in readings:
                sensors.append(f"{sensor}.{reading.label}")

        discovery = Discovery(
            key="psutil.sensors.discovery", macros="{#TEMPERATURE}",
            values=sensors
        )

        self._report(discovery)

    def _per_nic_stats(self):
        nic_stats = psutil.net_if_stats()
        timestamp = self.timestamp()

        for nic, stats in nic_stats.items():
            nic_items = {
                "isup": int(stats.isup),
                "duplex": stats.duplex,
                "speed": stats.speed,
                "mtu": stats.mtu,
            }
            data = Data(items=nic_items, key="psutil.net", append_key=f"[{nic}]", timestamp=timestamp)
            self._report(data)

    def _per_nic_io_counters(self):
        nic_counters = psutil.net_io_counters(pernic=True)
        timestamp = self.timestamp()

        for nic, counters in nic_counters.items():
            nic_items = {
                "bytes_recv": counters.bytes_recv,
                "bytes_sent": counters.bytes_sent,
                "packets_recv": counters.packets_recv,
                "packets_sent": counters.packets_sent,
                "dropin": counters.dropin,
                "dropout": counters.dropout,
                "errin": counters.errin,
                "errout": counters.errout,
            }
            data = Data(items=nic_items, key="psutil.net", append_key=f"[{nic}]", timestamp=timestamp)
            self._report(data)

    def _per_nic_addresses(self):
        nic_addresses = psutil.net_if_addrs()
        timestamp = self.timestamp()

        for nic, addresses in nic_addresses.items():
            nic_items = {}

            for address in addresses:
                if address.family == IP4_ADDRESS_FAMILY:
                    ip4 = {
                        "ip4": {
                            "address": address.address,
                            "netmask": address.netmask,
                            "broadcast": address.broadcast,
                            "ptp": address.ptp,
                        }
                    }
                    nic_items.update(ip4)
                elif address.family == IP6_ADDRESS_FAMILY:
                    ip6 = {
                        "ip6": {
                            "address": address.address,
                            "netmask": address.netmask,
                            "broadcast": address.broadcast,
                            "ptp": address.ptp,
                        }
                    }
                    nic_items.update(ip6)

                data = Data(items=nic_items, key="psutil.net", append_key=f"[{nic}]", timestamp=timestamp, )
                self._report(data)

    def _per_cpu_usage(self):
        per_cpu_usage = psutil.cpu_percent(percpu=True)
        timestamp = self.timestamp()

        for index, usage in enumerate(per_cpu_usage):
            data = Data(
                items={"usage": usage},
                key="psutil.cpu",
                append_key=f"[{index}]",
                timestamp=timestamp,
            )
            self._report(data)

    def _per_cpu_frequency(self):
        per_cpu_frequency = psutil.cpu_freq(percpu=True)
        timestamp = self.timestamp()

        for index, frequency in enumerate(per_cpu_frequency):
            data = Data(
                items={"current": frequency.current},
                key="psutil.cpu.frequency",
                append_key=f"[{index}]",
                timestamp=timestamp,
            )
            self._report(data)

    def _per_disk_counters(self):
        per_disk_counters = psutil.disk_io_counters(perdisk=True, nowrap=False)
        timestamp = self.timestamp()

        for disk, counters in per_disk_counters.items():
            if self._is_disk_useful(disk):
                data = Data(
                    items={
                        "read_count": counters.read_count,
                        "write_count": counters.write_count,
                        "read_bytes": counters.read_bytes,
                        "write_bytes": counters.write_bytes,
                        "read_time": counters.read_time,
                        "write_time": counters.write_time,
                    },
                    key="psutil.disk",
                    append_key=f"[{disk}]",
                    timestamp=timestamp,
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

    def _disks(self):
        disk_io = psutil.disk_io_counters(nowrap=True)

        data = Data(
            items={
                "read_count": disk_io.read_count,
                "write_count": disk_io.write_count,
                "read_bytes": disk_io.read_bytes,
                "write_bytes": disk_io.write_bytes,
                "read_time": disk_io.read_time,
                "write_time": disk_io.write_time,
            },
            key="psutil.disk",
            timestamp=self.timestamp(),
        )
        self._report(data)

        self._per_disk_counters()

    def _mountpoints(self):
        partitions = self._get_useful_partitions()
        timestamp = self.timestamp()

        for p in partitions:
            usage = psutil.disk_usage(p.mountpoint)
            data = Data(
                items={
                    "device": p.device,
                    "fstype": p.fstype,
                    "opts": p.opts,
                    "usage": {
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                },
                key="psutil.mountpoint",
                append_key=f"[{p.mountpoint}]",
                timestamp=timestamp,
            )
            self._report(data)

    def _temperature_sensors(self):
        temperature_sensors = psutil.sensors_temperatures(fahrenheit=False)
        timestamp = self.timestamp()

        for sensor, readings in temperature_sensors.items():
            for reading in readings:
                data = Data(
                    items={
                        "current": reading.current,
                    },
                    key="psutil.sensors.temperature",
                    append_key=f"[{sensor}.{reading.label}]",
                    timestamp=timestamp,
                )
                self._report(data)

    def _networks(self):
        net_io = psutil.net_io_counters()

        data = Data(
            items={
                "bytes_recv": net_io.bytes_recv,
                "bytes_sent": net_io.bytes_sent,
                "packets_recv": net_io.packets_recv,
                "packets_sent": net_io.packets_sent,
                "dropin": net_io.dropin,
                "dropout": net_io.dropout,
                "errin": net_io.errin,
                "errout": net_io.errout,
            },
            key="psutil.net",
            timestamp=self.timestamp(),
        )
        self._report(data)

        self._per_nic_stats()
        self._per_nic_addresses()
        self._per_nic_io_counters()
