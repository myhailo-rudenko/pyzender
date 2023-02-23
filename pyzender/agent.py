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
            debug_mode: bool = False,
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
        self.modules = modules
        self.report_queue = []
        self.report_count = 0
        self.debug_mode = debug_mode
        self.data_queue = {}
        self.data_thread = Thread(target=self._send_data_thread)

    def _send_discovery(self, discovery: DiscoveryReport) -> None:
        if discovery.values:
            hostname = self.hostname if discovery.hostname == "default" else discovery.hostname
            server = self.zabbix_server if discovery.server == "default" else discovery.server

            sender_data = [{discovery.macros: value} for value in discovery.values]
            sender_args = [
                self.sender_path,
                "--zabbix-server",
                server,
                "--host",
                hostname,
                "--key",
                discovery.key,
                "--value",
                json.dumps(sender_data),
            ]

            if self.debug_mode:
                print(f"Send discovery events to '{hostname}' via {server}: {sender_data}")

            try:
                subprocess.check_output(sender_args)
            except Exception as e:
                print("Error while sending values:", str(e))

    def _send_data(self):
        """
        Communicate with Zabbix Sender process (up to 250 values in one connection)
        """

        for group, data_lines in self.data_queue.items():
            hostname, server = group.split("@")

            hostname = self.hostname if hostname == "default" else hostname
            server = self.zabbix_server if server == "default" else server

            sender_args = [
                self.sender_path,
                "--zabbix-server",
                server,
                "--with-timestamps",
                "--host",
                hostname,
                "--input-file",
                "-",
            ]

            while len(data_lines) >= 250:
                try:
                    zabbix_sender = subprocess.Popen(
                        sender_args, stdout=subprocess.PIPE, stdin=subprocess.PIPE
                    )
                except Exception as e:
                    print("Unable to open Zabbix Sender process:", str(e))
                    sys.exit(1)

                data_portion = data_lines[:250]
                del data_lines[:250]

                sender_data = "".join(data_portion)

                if self.debug_mode:
                    print(f"Send items data to '{hostname}' via {server}: \n{sender_data}")

                try:
                    zabbix_sender.communicate(bytes(sender_data, "UTF-8"))
                except Exception as e:
                    print("Error while sending values:", str(e))

    def _send_data_thread(self) -> None:
        print(f"Starting data thread.")
        while True:
            time.sleep(1)
            self._send_data()

    def _update_data_queue(self, data_report: DataReport, recursive_dict: dict = {}, recursive_key_path: str = ""):
        group = f"{data_report.hostname}@{data_report.server}"
        if group not in self.data_queue.keys():
            self.data_queue.update({group: []})

        dict_ = recursive_dict or data_report.items

        for dict_key, value in dict_.items():

            if value is None:
                value = 0

            if recursive_key_path == "":
                key_path = ".".join([data_report.key, dict_key])
            else:
                key_path = ".".join([recursive_key_path, dict_key])

            if isinstance(value, dict):
                self._update_data_queue(data_report=data_report, recursive_dict=value, recursive_key_path=key_path)

            else:
                if data_report.append_key:
                    key_path = ".".join([key_path, data_report.append_key])

                line = f'- {key_path} {data_report.timestamp} "{value}"\r\n'
                self.data_queue[group].append(line)

    def run(self, send_interval: int = 1):
        for module in self.modules:
            module.run(agent=self)

        self.data_thread.start()

        while True:
            time.sleep(send_interval)

            while len(self.report_queue) > 0:
                report = self.report_queue.pop(0)

                if isinstance(report, DataReport):
                    self._update_data_queue(report)
                elif isinstance(report, DiscoveryReport):
                    self._send_discovery(report)
