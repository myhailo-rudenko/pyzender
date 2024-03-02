import configparser
import inspect
import json
import logging
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import uuid
from ast import literal_eval
from logging.handlers import RotatingFileHandler
from threading import Thread

from pydantic import BaseModel, Field, ValidationError

from pyzender import modules as pyzender_modules
from pyzender.modules.base import DiscoveryReport, DataReport, Module

file_handler = RotatingFileHandler(
    filename='/var/log/pyzender.log',
    maxBytes=10485760,
    backupCount=4,
)

logging.basicConfig(
    handlers=[file_handler],
    encoding='utf-8',
    level=logging.NOTSET,
    format='%(asctime)s | %(levelname)s | %(threadName)s | %(name)s.%(funcName)s | %(message)s',
    datefmt='%F %T'
)

logger = logging.getLogger()


def timestamp() -> int:
    return int(time.time())


class PyzenderError(Exception):
    pass


class AgentConfig(BaseModel):
    """
    hostname - The name of the host that will receive the statistics.
               It is configured on the Zabbix Server on the page: "Configuration" > "Hosts".
    zabbix_address - The IP address of the Zabbix Server or Zabbix Proxy.
    sender_path - Path to the zabbix_sender binary
    """
    hostname: str = Field(..., pattern=r"^[0-9A-za-z\.\s_-]+$")
    zabbix_server_host: str
    zabbix_server_port: int = Field(10051, ge=1024, lt=32767)
    zabbix_sender: str = Field(shutil.which("zabbix_sender"))
    queue_lookup_interval: int = Field(1, ge=1, le=600)
    queue_update_interval: int = Field(1, ge=1, le=600)
    queue_send_size: int = Field(150, ge=1, le=150)
    queue_max_send_interval: int = Field(10, ge=1, le=600)
    modules_sync_interval: int = Field(1, ge=1, le=600)
    debug_mode: bool = Field(False)
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
            logger.info(f"Module with name '{expected_name}' was found, arguments are: {kwargs}")
            try:
                return member(**kwargs)
            except ModuleNotFoundError:
                logger.error(
                    f"Dependencies for module '{expected_name}' are not installed. Install them manually or using "
                    "install.sh script."
                )


class Agent:
    def __init__(self, config_path: str = "/etc/pyzender/pyzender.conf"):
        self.uuid = uuid.uuid4()
        self.logger = logging.getLogger()
        logger.info(f"Starting the agent with UUID: {self.uuid}.")

        self.modules = list()
        self._read_config_file(path=config_path)

        self.report_queue = list()
        self.data_queue = {}
        self.discovery_queue = {}

        self.data_thread = Thread(name="MAIN: Data queue", target=self._data_thread)
        self.discovery_thread = Thread(name="MAIN: Discovery queue", target=self._discovery_thread)
        self.config_sync_thread = Thread(name="MAIN: Config sync", target=self._config_sync_thread)

        self.sent_total = 0
        self.failed_total = 0
        self.processed_total = 0
        self.last_sent_timestamp = timestamp()

    def _read_config_file(self, path: str):
        config_file = configparser.ConfigParser(strict=True, empty_lines_in_values=False, allow_no_value=False, )

        logger.info(f"Reading configuration file from: {path}")
        try:
            config_file.read(path)
            logger.info("Configuration file validation")
            self.config = AgentConfig(**configfile_to_dict(config_file, "agent"))
            for section in config_file.sections():
                module_kwargs = configfile_to_dict(config_file, section)
                module = find_module_by_name(section, **module_kwargs)
                if module:
                    self.modules.append(module)

        except configparser.Error as reason:
            logger.critical(f"Failed to read the config file! {str(reason)}")
            self.kill(str(reason))

        except ValidationError as reason:
            logger.critical(f"Validation failed! {str(reason)}")
            self.kill(str(reason))

        else:
            logger.info("Configuration file is valid and successfully initialized")

    def _send_data(self, this_is_a_data_queue: bool = False):
        """
        Communicate with Zabbix Sender process (up to 150 values in one connection)
        """
        queue = self.data_queue if this_is_a_data_queue else self.discovery_queue
        limit = self.config.keep_last_items if this_is_a_data_queue else self.config.keep_last_discovery

        timeout_reached = (timestamp() - self.last_sent_timestamp) >= self.config.queue_max_send_interval
        if timeout_reached:
            self.last_sent_timestamp = timestamp()

        items_in_queue = sum([len(data_lines) for _, data_lines in queue.items()])
        if items_in_queue:
            logger.info(
                f"Sending {'data' if this_is_a_data_queue else 'discovery events'} to the server."
                f" There are {len(queue.keys())} groups"
                f" and {items_in_queue} items in the queue."
            )

        processed = failed = sent = 0

        for group, data_lines in queue.items():
            this_is_a_discovery_queue = not this_is_a_data_queue
            data_queue_is_full_enough = len(data_lines) >= self.config.queue_send_size
            it_has_at_least_one_item = len(data_lines) > 0

            if data_queue_is_full_enough or timeout_reached or (
                    it_has_at_least_one_item and this_is_a_discovery_queue):
                # Send data to the server until there is nothing left to send in this group
                while len(data_lines) > 0:
                    try:
                        sender_subprocess = subprocess.Popen(
                            self._get_sender_args(*group.split("@")),
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE
                        )
                    except (OSError, ValueError) as reason:
                        logger.error(f"Unable to open Zabbix Sender process. {str(reason)}")
                    else:
                        data_portion = []
                        while len(data_lines) > 0 and len(data_portion) < self.config.queue_send_size:
                            data_portion.append(data_lines.pop(0))

                        sender_data = "".join(data_portion)
                        try:
                            stdout, _ = sender_subprocess.communicate(bytes(sender_data, "UTF-8"), timeout=10)
                        except (subprocess.TimeoutExpired, OSError) as message:
                            logger.error(str(message))
                            data_lines += data_portion
                        else:
                            if self.config.debug_mode:
                                logger.debug(f"Sending data to the {group} host: \n{sender_data}")

                            re_search_stdout = re.search(
                                pattern="processed:\s(\d+);\sfailed:\s(\d+);.*sent:\s(\d+);",
                                string=str(stdout)
                            )

                            if re_search_stdout:
                                processed += int(re_search_stdout.group(1))
                                failed += int(re_search_stdout.group(2))
                                sent += int(re_search_stdout.group(3))

                            if re.search(pattern="warning", string=str(stdout), flags=re.IGNORECASE):
                                logger.warning(str(stdout))

                        sender_subprocess.kill()

            # Delete old data that exceeds the limit
            if len(data_lines) > limit:
                diff = len(data_lines) - limit
                del data_lines[0:diff]

        self.processed_total += processed
        self.failed_total += failed
        self.sent_total += sent

        if any([processed, failed, sent]):
            logger.info(
                f"processed: {processed} (total: {self.processed_total}); "
                f"failed: {failed} (total: {self.failed_total}); "
                f"sent: {sent} (total: {self.sent_total}). "
                f" The next turn will be in {self.config.queue_lookup_interval} seconds"
            )

    def _request_active_checks(self) -> list:
        address = (self.config.zabbix_server_host, self.config.zabbix_server_port)
        logger.info(f"Requesting a list of active checks from {address[0]}:{address[1]}")
        data = {
            "request": "active checks",
            "host": self.config.hostname,
        }
        utf8_encoded_json = json.dumps(data).encode('utf-8')
        zbx_header = b'ZBXD' + struct.pack("<BII", 0x01, len(utf8_encoded_json), 0)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(address)
                s.sendall(zbx_header + utf8_encoded_json)

                protocol = s.recv(4)
                if protocol != b'ZBXD':
                    raise PyzenderError(f"Wrong protocol! {protocol} != b'ZBXD'")

                flag = s.recv(1)
                if flag == b'\x01':
                    packet_size = 4
                elif flag == b'\x04':
                    packet_size = 8
                else:
                    raise PyzenderError(f"This flag is not supported by pyzender! Flag is: {flag}")

                datalen: bytes = s.recv(packet_size)
                # skip reserved section
                s.recv(packet_size)
                raw_data = s.recv(int.from_bytes(datalen, 'big'))

            decoded_data = literal_eval(raw_data.decode('utf-8'))
            if decoded_data != {} and decoded_data["response"] == "success" and "data" in decoded_data.keys():
                logger.info(f"Success! The next request will be in {self.config.modules_sync_interval} seconds")
                return decoded_data["data"]
            elif decoded_data['response'] == 'failed':
                raise PyzenderError(decoded_data["info"])
            else:
                raise PyzenderError('Unsupported response from Zabbix Server')

        except (OSError, PyzenderError) as reason:
            logger.error(f"Failed to receive active checks from Zabbix Server. {str(reason)}")
            return []

    def _sync_modules(self) -> None:
        logger.info("Starting to sync module configurations")
        active_checks = self._request_active_checks()
        # discovered_modules = set()

        for active_check in active_checks:
            chain = active_check["key"].split(".")

            if all([len(chain) == 4, chain[0] == "pyzender", chain[1] == "module"]):
                module_name = chain[2]
                param_name = chain[3]
                param_value = active_check["delay"]
                # discovered_modules.add(module_name)

                # add a new module and feed an argument to it
                if module_name not in self.active_modules():
                    logger.info(f"Received a new module name from the server: '{module_name}'")
                    new_module = find_module_by_name(module_name, **{param_name: param_value})
                    if new_module:
                        self.modules.append(new_module)
                    else:
                        logger.warning(
                            f"Can't find any module with name '{module_name}'."
                            f" Update your zabbix template or pyzender package"
                        )

                # update an argument for an existing module
                else:
                    for module in self.modules:
                        if module.name == module_name:
                            module.config[param_name] = param_value
                            break

        self._start_all_modules()

    def _start_all_modules(self):
        for module in self.modules:
            if not module.running:
                logger.info(f"Seems that '{module.name}' module is not running. Trying to start it")
                module.run(agent=self)

    def _data_thread(self) -> None:
        logger.info(f"Starting thread for sending items data.")
        while True:
            time.sleep(self.config.queue_lookup_interval)
            self._send_data(this_is_a_data_queue=True)

    def _discovery_thread(self) -> None:
        logger.info(f"Starting thread for sending discovery events.")
        while True:
            time.sleep(self.config.queue_lookup_interval)
            self._send_data()

    def _config_sync_thread(self) -> None:
        logger.info("Starting thread for config synchronization.")
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
            self.data_queue.update({group: list()})

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
            "--verbose",
            "--input-file", "-",
        ]

    def data_queue_size(self) -> int:
        return sum([len(lines) for _, lines in self.data_queue.items()])

    def discovery_queue_size(self) -> int:
        return sum([len(lines) for _, lines in self.discovery_queue.items()])

    def active_modules(self) -> set:
        return set(m.name for m in self.modules)

    def run(self):
        self.config_sync_thread.start()
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
        logger.critical(f"Critical Error! Application will be closed with a reason: {reason}")
        os.kill(os.getpid(), signal)
