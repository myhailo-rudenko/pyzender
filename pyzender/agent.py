import json
import subprocess
import sys
import time
from threading import Thread
from typing import List

from pyzender.modules.base import Module, DataReport, DiscoveryReport


class Agent:
    def __init__(
            self,
            hostname: str,
            zabbix_server: str,
            modules: List[Module],
            sender_path: str = "/usr/bin/zabbix_sender",
            debug_mode: int = 0,
            queue_lookup_interval: int = 1,
            queue_update_interval: int = 1,
            queue_send_size: int = 250,
            keep_last_items: int = 10000,
            keep_last_discovery: int = 100,
    ):
        """
        hostname - The name of the host that will receive the statistics.
                   It is configured on the Zabbix Server on the page: "Configuration" > "Hosts".
        zabbix_address - The IP address of the Zabbix Server or Zabbix Proxy.
        sender_path - Path to the zabbix_sender binary
        """
        self.hostname = hostname
        self.zabbix_server = zabbix_server
        self.sender_path = sender_path
        self.queue_lookup_interval = queue_lookup_interval
        self.queue_update_interval = queue_update_interval
        self.queue_send_size = queue_send_size if 0 < queue_send_size <= 250 else 250
        self.keep_last_items = keep_last_items if 1000 < keep_last_items else 1000
        self.keep_last_discovery = keep_last_discovery if 10 < keep_last_discovery else 10
        self.modules = modules
        self.report_queue = []
        self.report_count = 0
        self.debug_mode = debug_mode
        self.data_queue = {}
        self.data_thread = Thread(target=self._data_thread)
        self.discovery_queue = {}
        self.discovery_thread = Thread(target=self._discovery_thread)

    def _send_data(self, this_is_data_queue: bool = False):
        """
        Communicate with Zabbix Sender process (up to 250 values in one connection)
        """
        if this_is_data_queue:
            queue = self.data_queue
            limit = self.keep_last_items
        else:
            queue = self.discovery_queue
            limit = self.keep_last_discovery

        for group, data_lines in queue.items():
            sender_args = self._get_sender_args(*group.split("@"))

            broken = False
            this_is_a_discovery_queue = not this_is_data_queue

            data_queue_is_full_enough = len(data_lines) >= self.queue_send_size
            it_has_at_least_one_item = len(data_lines) > 0

            while not broken and (
                    data_queue_is_full_enough or (this_is_a_discovery_queue and it_has_at_least_one_item)):
                try:
                    zabbix_process = subprocess.Popen(
                        sender_args,
                        stdout=subprocess.PIPE,
                        stdin=subprocess.PIPE
                    )
                except Exception as e:
                    print("Unable to open Zabbix Sender process:", str(e))
                    sys.exit(1)

                data_portion = data_lines[0:self.queue_send_size]
                sender_data = "".join(data_portion)
                try:
                    zabbix_process.communicate(bytes(sender_data, "UTF-8"), timeout=10)
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error while sending values: {str(e)}")
                    broken = True
                    zabbix_process.kill()
                else:
                    del data_lines[0:self.queue_send_size]
                    if self.debug_mode:
                        print(f"Send data to {group}: \n{sender_data}")

                data_queue_is_full_enough = len(data_lines) >= self.queue_send_size
                it_has_at_least_one_item = len(data_lines) > 0

            if len(data_lines) > limit:
                diff = len(data_lines) - limit
                del data_lines[0:diff]

    def _data_thread(self) -> None:
        print(f"Starting thread for sending items data.")
        while True:
            time.sleep(self.queue_lookup_interval)
            self._send_data(this_is_data_queue=True)

    def _discovery_thread(self) -> None:
        print(f"Starting thread for sending discovery events.")
        while True:
            time.sleep(self.queue_lookup_interval)
            self._send_data()

    def _update_discovery_queue(self, report: DiscoveryReport):
        group = f"{report.hostname}@{report.server}"
        if group not in self.discovery_queue.keys():
            self.discovery_queue.update({group: []})

        value_in_json = json.dumps([{report.macros: value} for value in report.values])
        line = f'- {report.key} {report.timestamp} {value_in_json}\r\n'
        self.discovery_queue[group].append(line)

    def _update_data_queue(self, report: DataReport, recursive_dict: dict = {}, recursive_key_path: str = ""):
        group = f"{report.hostname}@{report.server}"
        if group not in self.data_queue.keys():
            self.data_queue.update({group: []})

        dict_ = recursive_dict or report.items

        for dict_key, value in dict_.items():
            if value is None:
                value = 0

            if recursive_key_path == "":
                key_path = ".".join([report.key, dict_key])
            else:
                key_path = ".".join([recursive_key_path, dict_key])

            if isinstance(value, dict):
                self._update_data_queue(report=report, recursive_dict=value, recursive_key_path=key_path)

            else:
                if report.append_key:
                    key_path = ".".join([key_path, report.append_key])

                line = f'- {key_path} {report.timestamp} "{value}"\r\n'
                self.data_queue[group].append(line)

    def _get_sender_args(self, server: str, hostname: str) -> list:
        if hostname == "default":
            hostname = self.hostname

        if server == "default":
            server = self.zabbix_server

        return [
            self.sender_path,
            "--zabbix-server", server,
            "--host", hostname,
            "--with-timestamps",
            "--input-file", "-",
        ]

    def data_queue_size(self) -> int:
        return sum([len(lines) for _, lines in self.data_queue.items()])

    def discovery_queue_size(self) -> int:
        return sum([len(lines) for _, lines in self.discovery_queue.items()])

    def run(self):
        for module in self.modules:
            module.run(agent=self)

        self.data_thread.start()
        self.discovery_thread.start()

        while True:
            time.sleep(self.queue_update_interval)

            while len(self.report_queue) > 0:
                report = self.report_queue.pop(0)

                if isinstance(report, DataReport):
                    self._update_data_queue(report)
                elif isinstance(report, DiscoveryReport):
                    self._update_discovery_queue(report)
