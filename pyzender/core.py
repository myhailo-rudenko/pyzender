import json
import subprocess
import sys
import time


def send_discovery_data(
    server: str,
    discovery_key: str,
    macros_key: str,
    value_list: list,
    hostname: str,
    sender_path: str = "/usr/bin/zabbix_sender",
) -> None:
    discovery_data = [{macros_key: value} for value in value_list]
    sender_args = [sender_path, "--zabbix-server", server]
    if hostname:
        sender_args += ["--host", hostname]
    sender_args += [
        "--key",
        discovery_key,
        "--value",
        str(json.dumps({"data": discovery_data})),
    ]

    # Send discovery data
    try:
        if discovery_data != []:
            print(f"Send discovery data to '{hostname}' via {server}: \n{discovery_data}\n")
            subprocess.check_output(sender_args)
    except Exception as e:
        print("Error while sending discovery data:", str(e))


def send_item_data(
    server: str,
    dict_data: dict,
    hostname: str,
    root_key: str,
    last_key: str = "",
    timestamp: int = int(time.time()),
    with_timestamps: bool = True,
    sender_path: str = "/usr/bin/zabbix_sender",
) -> None:

    sender_args = [sender_path, "--zabbix-server", server]
    if with_timestamps:
        sender_args += ["--with-timestamps"]
    if hostname:
        sender_args += ["--host", hostname]
    sender_args += ["--input-file", "-"]

    # Prepare STDIN data
    stdin_data = extract_dict_to_stdin(dict_data, timestamp, "", root_key, last_key)
    if stdin_data != "":
        # Open Zabbix Sender process
        try:
            zabbix_sender = subprocess.Popen(sender_args, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        except Exception as e:
            print("Unable to open Zabbix Sender process:", str(e))
            sys.exit(1)

        # Send item data to STDIN of Zabbix Sender process (up to 250 values in one connection)
        print(f"Send items data to '{hostname}' via {server}: \n{stdin_data}\n")
        try:
            zabbix_sender.communicate(bytes(stdin_data, "UTF-8"))
        except Exception as e:
            print("Error while sending values:", str(e))


def extract_dict_to_stdin(
    dict_data: dict, timestamp: int, stdin_data: str = "", root_key: str = "", last_key: str = ""
) -> str:
    for key, value in dict_data.items():
        if value is None:
            value = 0
        key_path = f"{root_key}.{key}"
        if isinstance(value, dict):
            stdin_data = extract_dict_to_stdin(value, timestamp, stdin_data, key_path)
        else:
            key_path = f"{key_path}.{last_key}" if last_key else key_path
            line = f'- {key_path} {timestamp} "{value}"\r\n'
            stdin_data += line
    return stdin_data
