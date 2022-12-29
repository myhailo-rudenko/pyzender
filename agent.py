from pyzender import Agent
from pyzender.modules import PSUtil

psutil = PSUtil(data_interval=5, discovery_interval=5)
agent = Agent(receiver_hostname="test", receiver_address="192.168.0.3", modules=[psutil])

agent.run(0.2)
