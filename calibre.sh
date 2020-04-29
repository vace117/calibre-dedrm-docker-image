#!/bin/bash


docker rm calibre &> /dev/null

HOST_DIR="$HOME/.calibre_volume"
mkdir $HOST_DIR &> /dev/null
sudo chown :31382 $HOST_DIR
sudo chmod 775 $HOST_DIR
sudo chmod g+s $HOST_DIR
mkdir $HOST_DIR/.config &> /dev/null

docker run -it \
    -v /etc/localtime:/etc/localtime:ro \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$HOST_DIR":/home/calibre/calibre_volume \
    -e DISPLAY=unix"$DISPLAY" \
    --name calibre \
    vace117/calibre