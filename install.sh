#!/bin/bash
echo 'Copy pyZender script'
mkdir /opt/pyzender 2> /dev/null
cp agent.py /opt/pyzender/agent.py
chmod 644 /opt/pyzender/agent.py

echo 'Create pyZender service'
sudo bash -c 'cat << 'EOF' >/lib/systemd/system/pyzender.service
[Unit]
Description=pyZender service
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python /opt/pyzender/agent.py >> /dev/null
Restart=on-failure
User=${USER}

[Install]
WantedBy=multi-user.target
EOF'
sudo chmod 644 /lib/systemd/system/pyzender.service

echo 'Reload systemd'
sudo systemctl daemon-reload
sudo systemctl enable pyzender.service

echo 'Starting PyZender service'
sudo systemctl start pyzender.service
