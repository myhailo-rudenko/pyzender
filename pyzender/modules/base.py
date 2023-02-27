import time
from abc import ABC, abstractmethod
from threading import Thread
from typing import Optional, List, Union

from pydantic import BaseModel, Field


class DataReport(BaseModel):
    items: dict
    key: str = Field(..., description="example: 'qbittorrent.torrent'")
    append_key: str = Field("", description="example: f'[{name}]'")
    timestamp: int
    hostname: Optional[str] = Field("default")
    server: Optional[str] = Field("default")


class DiscoveryReport(BaseModel):
    key: str = Field(..., description="example: 'qbittorrent.torrent.discovery'")
    macros: str = Field(..., description="example: '{#TORRENT_NAME}'")
    values: List[str]
    hostname: Optional[str] = Field("default")
    server: Optional[str] = Field("default")


class Module(ABC):
    def __init__(
            self,
            data_interval: int = 60,
            discovery_interval: int = 300,
    ):
        self.name = self.__class__.__name__
        self.done = False
        self.agent = None
        self.data_thread = Thread(target=self._update_data, args=[int(data_interval)])
        self.discovery_thread = Thread(target=self._update_discovery, args=[int(discovery_interval)])

        print(f"'{self.name}' class initialized successfully.")

    @abstractmethod
    def _collect_data_reports(self) -> None:
        pass

    @abstractmethod
    def _collect_discovery_reports(self) -> None:
        pass

    @staticmethod
    def timestamp() -> int:
        return int(time.time())

    def _report(self, report: Union[DataReport, DiscoveryReport]):
        self.agent.report_queue.append(report)

    def _report_exception(self, message: str):
        print(f"'{self.name}' module has failed with an error: {message}")
        exception = DataReport(
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
        print(f"'{self.name}' module is running.")
        self.agent = agent
        self.discovery_thread.start()
        self.data_thread.start()

    def stop(self):
        print(f"'{self.name}' module has stopped.")
        self.done = True
        self.discovery_thread.join()
        self.data_thread.join()
