#!/bin/bash
echo 'Install zabbix-sender binary'
sudo apt update && sudo apt install zabbix-sender -y

echo 'Upgrade pyzender pip module'
pip install ./

echo 'Copy pyzender script to /var/lib/pyzender/agent.py'
sudo mkdir /var/lib/pyzender
sudo cp agent.py /var/lib/pyzender/agent.py

echo 'Copy pyzender configuration file to /etc/pyzender/pyzender.conf'
sudo mkdir /etc/pyzender
sudo cp pyzender.conf /etc/pyzender/pyzender.conf

export PYTHON3_PATH=$(which python3)

echo 'Copy pyzender service to /lib/systemd/system/pyzender.service'
bash -c 'cat << 'EOF' >/tmp/__pyzender.service
[Unit]
Description=pyZender service
After=multi-user.target

[Service]
Type=simple
ExecStart=${PYTHON3_PATH} /var/lib/pyzender/agent.py >> /dev/null
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
