#!/bin/bash
echo 'Install zabbix-sender binary'
sudo apt update && apt install zabbix-sender -y

echo 'Upgrade pyzender pip module'
pip install ./

echo 'Copy pyzender script to /opt/pyzender/agent.py'
mkdir /opt/pyzender 2> /dev/null
cp agent.py /opt/pyzender/agent.py
chmod 644 /opt/pyzender/agent.py

export PYTHON3_PATH=$(which python3)

echo 'Copy pyzender service to /lib/systemd/system/pyzender.service'
bash -c 'cat << 'EOF' >/tmp/__pyzender.service
[Unit]
Description=pyZender service
After=multi-user.target

[Service]
Type=simple
ExecStart=${PYTHON3_PATH} /opt/pyzender/agent.py >> /dev/null
Restart=on-failure
User=${USER}

[Install]
WantedBy=multi-user.target
EOF'

sudo mv /tmp/__pyzender.service /lib/systemd/system/pyzender.service
sudo chmod 644 /lib/systemd/system/pyzender.service

echo 'Reload systemd'
sudo systemctl daemon-reload
sudo systemctl enable pyzender.service

echo 'Restart pyzender service'
sudo systemctl restart pyzender.service
