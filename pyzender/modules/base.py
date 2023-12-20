import time
from abc import ABC, abstractmethod
from threading import Thread
from typing import List, Union


class DataReport:
    def __init__(
            self,
            items: dict,
            key: str,
            timestamp: int = int(time.time()),
            append_key: str = "",
            hostname: str = "default",
            port: str = "default",
            server: str = "default"
    ):
        self.items = items
        self.key = key
        self.timestamp = timestamp
        self.append_key = append_key
        self.hostname = hostname
        self.port = port
        self.server = server


class DiscoveryReport:
    def __init__(
            self,
            key: str,
            macros: str,
            values: List[str],
            hostname: str = "default",
            port: str = "default",
            server: str = "default"
    ):
        self.key = key
        self.macros = macros
        self.values = values
        self.timestamp = int(time.time())
        self.hostname = hostname
        self.port = port
        self.server = server


class Module(ABC):
    def __init__(
            self,
            data_interval: int = 60,
            discovery_interval: int = 300,
    ):
        self.name = self.__class__.__name__.lower()
        self.agent = None
        self.running = False
        self.data_interval = int(data_interval)
        self.discovery_interval = int(discovery_interval)
        self.data_thread = Thread(target=self._update_data, args=[])
        self.discovery_thread = Thread(target=self._update_discovery, args=[])
        self._import_dependencies()
        self.config = {}

        print(f"'{self.name}' class initialized successfully.")

    @abstractmethod
    def _collect_data_reports(self) -> None:
        pass

    @abstractmethod
    def _collect_discovery_reports(self) -> None:
        pass

    def _import_dependencies(self) -> None:
        pass

    @staticmethod
    def timestamp() -> int:
        return int(time.time())

    def _report(self, report: Union[DataReport, DiscoveryReport]):
        self.agent.report_queue.append(report)

    def _report_exception(self, message: str):
        print(f"'{self.name}' module has failed with an error: {message}")
        exception = DataReport(
            items={
                "exception": message
            },
            key="pyzender.health",
            timestamp=self.timestamp(),
        )
        self._report(exception)

    def _update_data(self):
        while True:
            time.sleep(self.data_interval)
            try:
                self._collect_data_reports()
            except Exception as msg:
                self._report_exception(str(msg))

    def _update_discovery(self):
        while True:
            time.sleep(self.discovery_interval)
            try:
                self._collect_discovery_reports()
            except Exception as msg:
                self._report_exception(str(msg))

    def run(self, agent):
        print(f"'{self.name}' module is running.")
        self.agent = agent
        self.running = True
        self.discovery_thread.start()
        self.data_thread.start()
