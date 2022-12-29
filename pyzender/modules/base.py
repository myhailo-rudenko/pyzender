import time
from abc import ABC, abstractmethod
from threading import Thread
from typing import Union

from ..models import Data, Discovery


class Module(ABC):
    def __init__(
        self,
        data_interval: int = 60,
        discovery_interval: int = 300,
    ):
        self.data_thread = Thread(target=self._update_data, args=[data_interval])
        self.discovery_thread = Thread(target=self._update_discovery, args=[discovery_interval])

    @abstractmethod
    def _collect_data_reports(self):
        pass

    @abstractmethod
    def _collect_discovery_reports(self):
        pass

    @staticmethod
    def timestamp() -> int:
        return int(time.time())

    def _report(self, report: Union[Data, Discovery]):
        self.agent.report_queue.append(report)

    def _report_exception(self, message: str) -> Data:
        exception = Data(
            items={"availability": 1, "exception": message},
            key="pyzagent",
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
        self.done = False
        self.agent = agent
        print("Start discovery thread.")
        self.discovery_thread.start()
        print("Start data thread.")
        self.data_thread.start()

    def stop(self):
        self.done = True
        self.discovery_thread.join()
        self.data_thread.join()
