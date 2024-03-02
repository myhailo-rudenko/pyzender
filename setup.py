from setuptools import setup

setup(
    name="pyZender",
    version="0.4.2-dev",
    description="Simple agent to send data via Zabbix Sender binary",
    author="Myhailo Rudenko",
    author_email="myhailo.rudenko@gmail.com",
    license="MIT",
    packages=["pyzender", "pyzender.modules"],
    install_requires=[
        "psutil>=5.9.1",
        "pydantic>=1.8.2",
        "qbittorrent-api>=2022.4.30",
    ],
)
