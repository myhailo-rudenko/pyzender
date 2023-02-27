#!/bin/bash
echo 'Stopping pyZender service'
systemctl stop pyzender.service 2> /dev/null

echo 'Remove pyZender service from systemd'
rm /lib/systemd/system/pyzender.service 2> /dev/null

echo 'Reload systemd'
systemctl daemon-reload

echo 'Remove directory /var/lib/pyzender'
rm /var/lib/pyzender -rf 2> /dev/null

echo 'Uninstall pyzender module from python3-pip'
pip uninstall pyzender