import json
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from threading import Thread
from typing import List, Optional, Union

import psutil
from pydantic import BaseModel, Field


class Data(BaseModel):
    items: dict
    key: str = Field(..., description="example: 'qbittorrent.torrent'")
    append_key: str = Field("", description="example: f'[{name}]'")
    timestamp: int
    receiver_hostname: Optional[str]
    receiver_address: Optional[str]


class Discovery(BaseModel):
    key: str = Field(..., description="example: 'qbittorrent.torrent.discovery'")
    macros: str = Field(..., description="example: '{#TORRENT_NAME}'")
    values: List[str]
    receiver_hostname: Optional[str]
    receiver_address: Optional[str]


class Module(ABC):
    def __init__(
            self,
            data_interval: int = 60,
            discovery_interval: int = 300,
    ):
        self.done = False
        self.agent = None
        self.data_thread = Thread(target=self._update_data, args=[data_interval])
        self.discovery_thread = Thread(target=self._update_discovery, args=[discovery_interval])

    @abstractmethod
    def _collect_data_reports(self) -> None:
        pass

    @abstractmethod
    def _collect_discovery_reports(self) -> None:
        pass

    @staticmethod
    def timestamp() -> int:
        return int(time.time())

    def _report(self, report: Union[Data, Discovery]):
        self.agent.report_queue.append(report)

    def _report_exception(self, message: str) -> Data:
        exception = Data(
            items={"availability": 1, "exception": message},
            key="pyzender",
            timestamp=self.timestamp(),
        )
        self._report(exception)

    def _update_data(self, data_interval: int):
        while not self.done:
            time.sleep(data_interval)
            try:
                self._collect_data_reports()
            except Exception as msg:
                self._report_exception(str(msg))

    def _update_discovery(self, discovery_interval: int):
        while not self.done:
            time.sleep(discovery_interval)
            try:
                self._collect_discovery_reports()
            except Exception as msg:
                self._report_exception(str(msg))

    def run(self, agent):
        self.agent = agent
        self.discovery_thread.start()
        self.data_thread.start()

    def stop(self):
        self.done = True
        self.discovery_thread.join()
        self.data_thread.join()


class Agent:
    def __init__(
            self,
            receiver_hostname: str,
            receiver_address: str,
            modules: List[Module],
            sender_path: str = "/usr/bin/zabbix_sender",
    ):
        """
        receiver_hostname - The name of the host that will receive the statistics.
                            It is configured on the Zabbix Server on the page: "Configuration" > "Hosts".
        receiver_address - The IP address of the Zabbix Server or Zabbix Proxy.
        sender_path - Path to the zabbix_sender binary
        """

        self.receiver_hostname = receiver_hostname
        self.receiver_address = receiver_address
        self.sender_path = sender_path
        self.modules = modules
        self.report_queue = []

    def _send_discovery(self, discovery: Discovery) -> None:
        """
        Communicate with Zabbix Sender process (up to 250 values in one connection)
        """

        if discovery.values:
            sender_data = [{discovery.macros: value} for value in discovery.values]
            sender_args = [
                self.sender_path,
                "--zabbix-server",
                discovery.receiver_address or self.receiver_address,
                "--host",
                discovery.receiver_hostname or self.receiver_hostname,
                "--key",
                discovery.key,
                "--value",
                json.dumps(sender_data),
            ]
            print(
                f"Send discovery events to '{self.receiver_hostname}' via {self.receiver_address}: \n{sender_data}"
            )

            try:
                subprocess.check_output(sender_args)
            except Exception as e:
                print("Error while sending values:", str(e))

    def _send_data(self, data: Data) -> None:
        """
        Communicate with Zabbix Sender process (up to 250 values in one connection)
        """

        if data.items:
            sender_data = self._extract(data.items, data.timestamp, "", data.key, data.append_key)
            sender_args = [
                self.sender_path,
                "--zabbix-server",
                data.receiver_address or self.receiver_address,
                "--with-timestamps",
                "--host",
                data.receiver_hostname or self.receiver_hostname,
                "--input-file",
                "-",
            ]
            print(
                f"Send items data to '{self.receiver_hostname}' via {self.receiver_address}: \n{sender_data}"
            )

            try:
                zabbix_sender = subprocess.Popen(
                    sender_args, stdout=subprocess.PIPE, stdin=subprocess.PIPE
                )
            except Exception as e:
                print("Unable to open Zabbix Sender process:", str(e))
                sys.exit(1)

            try:
                zabbix_sender.communicate(bytes(sender_data, "UTF-8"))
            except Exception as e:
                print("Error while sending values:", str(e))

    def _extract(
            self,
            dict_data: dict,
            timestamp: int,
            stdin_data: str = "",
            key: str = "",
            append_key: str = "",
    ) -> str:
        """
        Extract dictionary to stdin accepted by zabbix_sender binary
        """

        for dict_key, value in dict_data.items():
            if value is None:
                value = 0
            key_path = f"{key}.{dict_key}"
            if isinstance(value, dict):
                stdin_data = self._extract(value, timestamp, stdin_data, key_path, append_key)
            else:
                key_path = f"{key_path}.{append_key}" if append_key else key_path
                line = f'- {key_path} {timestamp} "{value}"\r\n'
                stdin_data += line
        return stdin_data

    def run(self, send_interval: int = 1):
        for module in self.modules:
            module.run(agent=self)

        while True:
            time.sleep(send_interval)
            print(f"Report queue: [{len(self.report_queue)}]")
            while len(self.report_queue) > 0:
                report = self.report_queue.pop(0)
                if hasattr(report, "items"):
                    self._send_data(report)
                elif hasattr(report, "values"):
                    self._send_discovery(report)


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
                "syscalls": stats.syscalls,
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
