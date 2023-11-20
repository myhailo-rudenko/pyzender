import configparser
import inspect
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
from ast import literal_eval
from ipaddress import IPv4Address
from threading import Thread

from pydantic import BaseModel, Field

from pyzender import modules as pyzender_modules
from pyzender.modules.base import DiscoveryReport, DataReport, Module


class AgentConfig(BaseModel):
    """
    hostname - The name of the host that will receive the statistics.
               It is configured on the Zabbix Server on the page: "Configuration" > "Hosts".
    zabbix_address - The IP address of the Zabbix Server or Zabbix Proxy.
    sender_path - Path to the zabbix_sender binary
    """
    hostname: str = Field(..., pattern=r"^[0-9A-za-z\.\s_-]+$", ge=1, le=128)
    zabbix_server_host: IPv4Address
    zabbix_server_port: int = Field(10051, ge=1024, lt=32767)
    zabbix_sender: str = Field(shutil.which("zabbix_sender"))
    queue_lookup_interval: int = Field(1, ge=1, le=600)
    queue_update_interval: int = Field(1, ge=1, le=600)
    modules_sync_interval: int = Field(1, ge=1, le=600)
    debug_mode: bool = Field(False)
    queue_send_size: int = Field(150, ge=1, le=150)
    keep_last_items: int = Field(1000, ge=100, le=1000000)
    keep_last_discovery: int = Field(10, ge=10, le=100)


def configfile_to_dict(config_file, section: str) -> dict:
    dict_ = {opt: config_file.get(section, opt) for opt in config_file.options(section)}
    for key, value in dict_.items():
        if isinstance(value, str) and value.isdigit():
            dict_[key] = int(value)

    return dict_


def find_module_by_name(expected_name: str, **kwargs) -> Module:
    for name, member in inspect.getmembers(pyzender_modules):
        if name.lower() == expected_name and issubclass(member, Module):
            print(f"Module with name '{expected_name}' was found")
            print(f"Arguments for the '{expected_name}' are: {kwargs}")
            try:
                return member(**kwargs)
            except ModuleNotFoundError:
                print(
                    f"Dependencies for module '{expected_name}' are not installed. Install them manually or using "
                    "install.sh script."
                )


class Agent:
    def __init__(self, config_path: str = "/etc/pyzender/pyzender.conf"):
        self.modules = []
        self._read_config_file(path=config_path)

        self.modules_by_name = []
        self.report_queue = []
        self.report_count = 0

        self.data_queue = {}
        self.discovery_queue = {}

        self.data_thread = Thread(target=self._data_thread)
        self.discovery_thread = Thread(target=self._discovery_thread)
        self.sync_modules_thread = Thread(target=self._sync_modules_thread)

    def _read_config_file(self, path: str):
        print(f"Reading configuration from: {path}")
        config_file = configparser.ConfigParser()
        config_file.read(path)
        self.config = AgentConfig(**configfile_to_dict(config_file, "agent"))

        for section in config_file.sections():
            module_kwargs = configfile_to_dict(config_file, section)
            module = find_module_by_name(section, **module_kwargs)
            self.modules.append(module)

    def _send_data(self, this_is_data_queue: bool = False):
        """
        Communicate with Zabbix Sender process (up to 150 values in one connection)
        """
        if this_is_data_queue:
            queue = self.data_queue
            limit = self.config.keep_last_items
        else:
            queue = self.discovery_queue
            limit = self.config.keep_last_discovery

        for group, data_lines in queue.items():
            sender_args = self._get_sender_args(*group.split("@"))

            broken = False
            this_is_a_discovery_queue = not this_is_data_queue

            data_queue_is_full_enough = len(data_lines) >= self.config.queue_send_size
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

                data_portion = data_lines[0:self.config.queue_send_size]
                sender_data = "".join(data_portion)
                try:
                    zabbix_process.communicate(bytes(sender_data, "UTF-8"), timeout=10)
                except Exception as e:
                    if self.config.debug_mode:
                        print(f"Error while sending values: {str(e)}")
                    broken = True
                    zabbix_process.kill()
                else:
                    del data_lines[0:self.config.queue_send_size]
                    if self.config.debug_mode:
                        print(f"Send data to {group}: \n{sender_data}")

                data_queue_is_full_enough = len(data_lines) >= self.config.queue_send_size
                it_has_at_least_one_item = len(data_lines) > 0

            if len(data_lines) > limit:
                diff = len(data_lines) - limit
                del data_lines[0:diff]

    def _request_latest_active_checks(self) -> list:
        address = (self.config.zabbix_server_host, self.config.zabbix_server_port)
        data = {
            "request": "active checks",
            "host": self.config.hostname,
        }
        utf8_data_in_json = json.dumps(data).encode('utf-8')
        zbx_header = b'ZBXD' + struct.pack("<BII", 0x01, len(utf8_data_in_json), 0)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(address)
                s.sendall(zbx_header + utf8_data_in_json)

                protocol = s.recv(4)
                if protocol != b'ZBXD':
                    print(f"Wrong protocol! {protocol} != b'ZBXD'")
                    return []

                flag = s.recv(1)
                if flag == b'\x01':
                    packet_size = 4
                elif flag == b'\x04':
                    packet_size = 8
                else:
                    print(f"This flag is not supported by pyzender! Flag is: {flag}")
                    return []

                datalen: bytes = s.recv(packet_size)
                # skip reserved section
                s.recv(packet_size)

                raw_data = s.recv(int.from_bytes(datalen, 'big'))

        except Exception as reason:
            self.kill(str(reason))

        decoded_data = literal_eval(raw_data.decode('utf-8'))

        if decoded_data != {} and decoded_data["response"] == "success" and "data" in decoded_data.keys():
            return decoded_data["data"]

        elif decoded_data['response'] == 'failed':
            print(
                f'Failed to receive active checks for "{self.config.hostname}" host with the reason: '
                f'{decoded_data["info"]}'
            )
        else:
            print(f'Unsupported response from Zabbix server')

        return []

    def _sync_modules(self) -> None:
        active_checks = self._request_latest_active_checks()

        for active_check in active_checks:
            chain = active_check["key"].split(".")

            if all([len(chain) == 4, chain[0] == "pyzender", chain[1] == "module"]):
                module_name = chain[2]
                param_name = chain[3]
                param_value = active_check["delay"]

                # add a new module and feed an argument to it
                if module_name not in [m.name for m in self.modules]:
                    new_module = find_module_by_name(module_name, **{param_name: param_value})
                    if new_module:
                        self.modules.append(new_module)

                # update an argument for an existing module
                else:
                    for module in self.modules:
                        if module.name == module_name:
                            module.config[param_name] = param_value
                            break

        for module in self.modules:
            if not module.running:
                module.run()

    def _data_thread(self) -> None:
        print(f"Starting thread for sending items data.")
        while True:
            time.sleep(self.config.queue_lookup_interval)
            self._send_data(this_is_data_queue=True)

    def _discovery_thread(self) -> None:
        print(f"Starting thread for sending discovery events.")
        while True:
            time.sleep(self.config.queue_lookup_interval)
            self._send_data()

    def _sync_modules_thread(self) -> None:
        print("Starting thread for config synchronization.")
        while True:
            time.sleep(self.config.modules_sync_interval)
            self._sync_modules()

    def _update_discovery_queue(self, report: DiscoveryReport):
        group = f"{report.hostname}@{report.server}:{report.port}"
        if group not in self.discovery_queue.keys():
            self.discovery_queue.update({group: []})

        value_in_json = json.dumps([{report.macros: value} for value in report.values])
        line = f'- {report.key} {report.timestamp} {value_in_json}\r\n'
        self.discovery_queue[group].append(line)

    def _update_data_queue(
            self,
            report: DataReport,
            recursive_dict: dict = {},
            recursive_key_path: str = ""
    ):
        group = f"{report.hostname}@{report.server}:{report.port}"
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

    def _get_sender_args(self, hostname: str, server: str) -> list:
        if hostname == "default":
            hostname = self.config.hostname

        server, port = server.split(":")
        if server == "default":
            server = self.config.zabbix_server_host

        if port == "default":
            port = self.config.zabbix_server_port

        return [
            self.config.zabbix_sender,
            "--zabbix-server", server,
            "--host", hostname,
            "--port", str(port),
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

        self.sync_modules_thread.start()
        self.data_thread.start()
        self.discovery_thread.start()

        while True:
            time.sleep(self.config.queue_update_interval)

            while len(self.report_queue) > 0:
                report = self.report_queue.pop(0)

                if isinstance(report, DataReport):
                    self._update_data_queue(report)
                elif isinstance(report, DiscoveryReport):
                    self._update_discovery_queue(report)

    @staticmethod
    def kill(reason: str = "", signal: int = 9):
        print(f"Critical Error! Application will be closed with a reason: {reason}")
        os.kill(os.getpid(), signal)
