#!/usr/bin/python3

from pyzender import Agent
from pyzender.modules import PSUtil, Health, QBittorrent

health = Health(data_interval=10)
psutil = PSUtil(data_interval=5, discovery_interval=300)
qbittorrent = QBittorrent(
    data_interval=5,
    discovery_interval=300,
    host="192.168.0.4",
    port=8080,
)

modules = [psutil, health, qbittorrent]
agent = Agent(hostname="test", zabbix_server="192.168.0.3", modules=modules, debug_mode=True)

agent.run(1)
