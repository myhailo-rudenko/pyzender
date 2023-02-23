import qbittorrentapi

from pyzender.modules.base import Module, DiscoveryReport, DataReport


class QBittorrent(Module):
    def __init__(
            self,
            host: str,
            port: int,
            username: str = "",
            password: str = "",
            data_interval: int = 60,
            discovery_interval: int = 300,
            verify_ssl: bool = False
    ):
        super(QBittorrent, self).__init__(data_interval, discovery_interval)

        # the Client will automatically acquire/maintain a logged-in state in line with any request.
        self.qbt_client = qbittorrentapi.Client(
            host=host,
            port=port,
            username=username,
            password=password,
            VERIFY_WEBUI_CERTIFICATE=verify_ssl,
        )

        # self.max_name_len = 60
        # self.separator = "..."
        #
        # self.left_part_len = self.max_name_len // 2
        # self.right_part_len = self.max_name_len - self.left_part_len - len(self.separator)

    @staticmethod
    def _fix_name(torrent_name: str) -> str:
        name = torrent_name.replace(" ", "_").replace("[", "(").replace("]", ")").replace(",", ".")
        # if len(name) > self.max_name_len:
        #     name = f"{name[:self.left_part_len]}{self.separator}{name[-self.right_part_len:]}"
        return name

    def _collect_data_reports(self):
        self.per_torrent_info()

    def _collect_discovery_reports(self):
        self.discover_torrents()

    def discover_torrents(self):
        torrents = [self._fix_name(t.info.name) for t in self.qbt_client.torrents.info()]

        discovery = DiscoveryReport(
            key="qbittorrent.torrent.discovery", macros="{#TORRENT_NAME}",
            values=torrents
        )

        self._report(discovery)

    def per_torrent_info(self):
        timestamp = self.timestamp()

        for torrent in self.qbt_client.torrents.info():
            name = self._fix_name(torrent.info.name)
            data = DataReport(
                items=dict(torrent.info),
                key="qbittorrent.torrent",
                append_key=f"[{name}]",
                timestamp=timestamp,
            )
            self._report(data)
