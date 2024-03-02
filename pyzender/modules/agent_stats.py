from pyzender.modules.base import Module, DataReport


class AgentStats(Module):
    def _collect_data_reports(self):
        self._agent_health()

    def _collect_discovery_reports(self):
        pass

    def _agent_health(self):
        health = DataReport(
            items={
                "running": 1,
                "processed": self.agent.processed,
                "failed": self.agent.failed,
                "sent": self.agent.sent,
                "queue": sum(
                    [len(data_lines) for _, data_lines in self.agent.data_queue.items()]
                    + [len(data_lines) for _, data_lines in self.agent.discovery_queue.items()]
                )
            },
            key="pyzender",
            timestamp=self.timestamp(),
        )
        self._report(health)
