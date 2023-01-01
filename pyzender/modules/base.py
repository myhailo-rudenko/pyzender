import time
from abc import ABC, abstractmethod
from threading import Thread
from typing import Optional, List, Union

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

    def _report_exception(self, message: str):
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
