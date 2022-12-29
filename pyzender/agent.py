import json
import subprocess
import sys
import time
from typing import List

from .models import Data, Discovery
from .modules import Module


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

        if discovery.values != []:
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

        if data.items != {}:
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

    # set as daemon thread?
    def run(self, send_interval: int = 1):
        for module in self.modules:
            module.run(agent=self)

        while True:
            time.sleep(send_interval)
            print(f"Report queue: [{len(self.report_queue)}]")
            while len(self.report_queue) > 0:
                report = self.report_queue.pop(0)
                if isinstance(report, Data):
                    self._send_data(report)
                elif isinstance(report, Discovery):
                    self._send_discovery(report)
