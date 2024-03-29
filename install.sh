#!/bin/bash

export SUDO=$(which sudo)

$SUDO apt update
$SUDO apt install jq zabbix-sender python3-venv

while true; do
    read -p "Do you want to download and install the pyzender service? [Y/n]: " answer
    case $answer in
        "" | [yY] ) install=true  ; break   ;;
        [nN] )      install=false ; break   ;;
        * )         echo "invalid response" ;;
    esac
  done

if $install; then
  DOWNLOAD_DIR="$HOME/opt"
  if ! [ -d $DOWNLOAD_DIR ]; then
    mkdir $DOWNLOAD_DIR
  fi

  echo "Repository: https://github.com/myhailo-rudenko/pyzender"
  REPO_TAGS=$(curl -sL https://api.github.com/repos/myhailo-rudenko/pyzender/tags | jq -r ".[].name")
  echo "Tags:" && echo "$REPO_TAGS"
  echo "This script is compatible with tags: v0.4.*"
  read -p "What tag do you want to download from GitHub repo?: " REPO_TAG

  wget --progress=bar --continue --directory-prefix=$DOWNLOAD_DIR https://github.com/myhailo-rudenko/pyzender/archive/refs/tags/$REPO_TAG.tar.gz
  TAR_STDOUT=$(tar xvf $DOWNLOAD_DIR/$REPO_TAG.tar.gz --directory $DOWNLOAD_DIR)
  PKG_DIR=$DOWNLOAD_DIR/$(echo "$TAR_STDOUT" | head -n 1)

  python3 -m venv $HOME/.virtualenvs/pyzender-${REPO_TAG}.venv
  source $HOME/.virtualenvs/pyzender-${REPO_TAG}.venv/bin/activate
  pip install $PKG_DIR
  deactivate
fi

ETC_CONFIG_DIR="/etc/pyzender"
export ETC_CONFIG_FILE="$ETC_CONFIG_DIR/pyzender.conf"
PKG_CONFIG_FILE=$PKG_DIR"pyzender.conf"

echo $ETC_CONFIG_DIR
echo $ETC_CONFIG_FILE
echo $PKG_CONFIG_FILE

if ! [ -d "$ETC_CONFIG_DIR" ]; then
  $SUDO mkdir $ETC_CONFIG_DIR

elif ! [ -f "$ETC_CONFIG_FILE" ]; then
  $SUDO cp $PKG_CONFIG_FILE $ETC_CONFIG_FILE

else
  if cmp --silent -- "$PKG_CONFIG_FILE" "$ETC_CONFIG_FILE"; then
    echo "files contents are identical"
  else
    echo "files differ"
  fi

  while true; do
    read -p "Config file already exists! Do you want to replace it? [y/N]: " answer
    case $answer in
        [yY] )      replace_config=true  ; break ;;
        "" | [nN] ) replace_config=false ; break ;;
        * )         echo "invalid response" ;;
    esac
  done

  if $replace_config; then
    $SUDO cp $PKG_CONFIG_FILE $ETC_CONFIG_FILE
  fi
fi

if ! [ -d /var/lib/pyzender ]; then
    $SUDO mkdir /var/lib/pyzender
fi

export PYTHON3_VENV=$HOME/.virtualenvs/pyzender-${REPO_TAG}.venv/bin/python

bash -c 'cat << 'EOF' >/tmp/__pyzender.service
[Unit]
Description=pyZender service
After=multi-user.target
[Service]
Type=simple
ExecStart=${PYTHON3_VENV} -c "from pyzender import Agent;Agent(\"${ETC_CONFIG_FILE}\").run()"
Restart=on-failure
User=${USER}
[Install]
WantedBy=multi-user.target
EOF'

$SUDO mv /tmp/__pyzender.service /lib/systemd/system/pyzender.service
$SUDO chmod 644 /lib/systemd/system/pyzender.service

echo "Service deployed to /lib/systemd/system/pyzender.service"

$SUDO systemctl daemon-reload
$SUDO systemctl enable pyzender.service
$SUDO systemctl restart pyzender.service

rm $PKG_DIR -rf

echo "Done!"