#!/bin/bash
echo "Remove old package"
cd /opt/pyzender
rm ./latest.tar.gz
rm ./pyzender-latest -rf 2> /dev/null

echo "Download the latest version of pyzender"
wget https://github.com/myhailo-rudenko/pyzender/archive/refs/tags/latest.tar.gz

tar xvf ./latest.tar.gz

cd ./pyzender-latest
. install.sh