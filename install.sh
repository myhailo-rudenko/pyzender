#!/bin/bash

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

  echo "Visit GitHub page to view available tags: https://github.com/myhailo-rudenko/pyzender/tags"
  read -p "What tag do you want to download from GitHub repo?: " repo_tag

  wget --progress=bar --continue --directory-prefix=$DOWNLOAD_DIR https://github.com/myhailo-rudenko/pyzender/archive/refs/tags/$repo_tag.tar.gz
  tar xvf $DOWNLOAD_DIR/$repo_tag.tar.gz --directory $DOWNLOAD_DIR

  PKG_DIR="$DOWNLOAD_DIR/pyzender-$repo_tag"
  echo $PKG_DIR
  pip install $PKG_DIR

  read -p "Pyzender require zabbix-sender binary to be installed. Do you want it to install now? [Y/n]: " answer
  case $answer in
      "" | [yY] ) $install_zabbix_binary=true  ;;
      [nN] )      $install_zabbix_binary=false ;;
      * )         echo "invalid response" ;;
  esac

  if $install_zabbix_binary; then
    sudo apt update && sudo apt install zabbix-sender -y
  fi

  ETC_CONFIG_DIR="/etc/pyzender"
  ETC_CONFIG_FILE="$ETC_CONFIG_DIR/pyzender.conf"
  PKG_CONFIG_FILE="$PKG_DIR/pyzender.conf"

  echo $ETC_CONFIG_DIR
  echo $ETC_CONFIG_FILE
  echo $PKG_CONFIG_FILE

  if ! [ -d "$ETC_CONFIG_DIR" ]; then
    sudo mkdir $ETC_CONFIG_DIR

  elif ! [ -f "$ETC_CONFIG_FILE" ]; then
    cp $PKG_CONFIG_FILE $ETC_CONFIG_FILE

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
      cp $PKG_CONFIG_FILE $ETC_CONFIG_FILE
    fi
  fi

  if ! [ -d /var/lib/pyzender ]; then
      sudo mkdir /var/lib/pyzender
  fi

  sudo cp $PKG_DIR/agent.py /var/lib/pyzender/agent.py
  export PYTHON3_PATH=$(which python3)
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

  sudo systemctl daemon-reload
  sudo systemctl enable pyzender.service
  sudo systemctl restart pyzender.service
fi