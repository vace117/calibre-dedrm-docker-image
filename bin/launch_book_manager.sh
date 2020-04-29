#!/bin/bash


docker rm calibre &> /dev/null

HOST_DIR="$HOME/Calibre_DeDRM_Volume"

if [ ! -f "$HOST_DIR/.PERMISSIONS_SET_MARKER" ] ; then
    mkdir $HOST_DIR &> /dev/null

    printf "\nYou will now be asked for your root password, which is needed to setup permissions on \
the directory which will be used to store this container's persistent data.\n 
The directory is: $HOST_DIR\n\n"

    sudo chown :31382 $HOST_DIR
    sudo chmod 775 $HOST_DIR
    sudo chmod g+s $HOST_DIR
    mkdir $HOST_DIR/.config

    sudo touch $HOST_DIR/.PERMISSIONS_SET_MARKER
fi

docker run -it \
    -v /etc/localtime:/etc/localtime:ro \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$HOST_DIR":/home/calibre/calibre_volume \
    -e DISPLAY=unix"$DISPLAY" \
    --name calibre \
    vace117/calibre-dedrm