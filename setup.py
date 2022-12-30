from setuptools import setup

setup(
    name="pyZender",
    version="0.2.3",
    description="Simple agent to send data via Zabbix Sender binary",
    author="Myhailo Rudenko",
    author_email="myhailo.rudenko@gmail.com",
    license="MIT",
    packages=["pyzender"],
    install_requires=[
        'psutil>=5.9.1',
        'pydantic>=1.8.2',
    ],
)
