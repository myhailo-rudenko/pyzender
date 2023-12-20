from pyzender.modules.base import Module, DataReport


class Health(Module):
    def _collect_data_reports(self):
        self._agent_health()

    def _collect_discovery_reports(self):
        pass

    def _agent_health(self):
        health = DataReport(
            items={
                "running": 1,
                "sent": self.agent.sent_lines,
                "queue": len(self.agent.report_queue)
            },
            key="pyzender.health",
            timestamp=self.timestamp(),
        )
        self._report(health)
