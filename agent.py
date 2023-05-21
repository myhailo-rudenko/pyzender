#!/usr/bin/python3
import configparser
import inspect

from pyzender import modules, Agent

# TODO: Fix file permissions
CONFIG_PATH = "/etc/pyzender/pyzender.conf"


def digits_to_int(dict_: dict) -> dict:
    for key, value in dict_.items():
        if isinstance(value, str) and value.isdigit():
            dict_[key] = int(value)

    return dict_


print(f"Reading configuration from: {CONFIG_PATH}")
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

agent_options = config.options("agent")
agent_kwargs = {o: config.get("agent", o) for o in agent_options}
agent_kwargs.update({"modules": []})
agent_kwargs = digits_to_int(agent_kwargs)

for name, obj in inspect.getmembers(modules):
    for section in config.sections():

        if name.lower() == section and inspect.isclass(obj):
            print(f"Class with name '{name}' was found")

            options = config.options(section)
            kwargs = {opt: config.get(section, opt) for opt in options}
            kwargs = digits_to_int(kwargs)

            print(f"Arguments for '{name}' class are: {kwargs}")
            try:
                module = obj(**kwargs)
            except ModuleNotFoundError as e:
                print(
                    f"Dependencies for module '{name}' are not installed. Install them manually or using install.sh "
                    "script."
                )
            else:
                agent_kwargs["modules"].append(module)
            break

agent = Agent(**agent_kwargs)
agent.run()
