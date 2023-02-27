#!/bin/bash
echo "Remove old package"
rm /opt/pyzender/pyzender-latest -rf 2> /dev/null

echo "Download the latest version of pyzender"
wget https://github.com/myhailo-rudenko/pyzender/archive/refs/tags/latest.tar.gz -P /opt/pyzender/

tar xvf /opt/pyzender/latest.tar.gz

cd /opt/pyzender/pyzender-latest
. install.sh