#!/bin/bash
echo 'Copy pyZender script'
mkdir /opt/pyzender 2> /dev/null
cp agent.py /opt/pyzender/agent.py
chmod 755 /opt/pyzender/agent.py
echo 'Create pyZender service'
cat << 'EOF' >/lib/systemd/system/pyzender.service
[Unit]
Description=pyZender service
After=multi-user.target
Conflicts=getty@tty1.service

[Service]
Type=simple
ExecStart=/usr/bin/python /opt/pyzender/agent.py
StandardInput=tty-force
Restart=on-failure
User=myhailo

[Install]
WantedBy=multi-user.target

EOF
sudo chmod 644 /lib/systemd/system/pyzender.service
echo 'Reload systemd'
systemctl daemon-reload
systemctl enable pyzender.service
echo 'Starting PyZender service'
systemctl start pyzender.service
