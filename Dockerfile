FROM ubuntu:eoan

ARG DEBIAN_FRONTEND=noninteractive

# Install Calibre
RUN apt-get update \
    && apt-get install -y --no-install-recommends -qq calibre

# Install 32-bit wine
RUN dpkg --add-architecture i386 && apt-get update \
    && apt-get install -y --no-install-recommends -qq wine wine32

# Install various tools and dependencies
RUN apt-get install -y --no-install-recommends -qq \
    wget \
    p7zip-full \
    tree \
    ca-certificates \
    cowsay \
    && rm -rf /var/lib/apt/lists/*
#################

# Setup a persistent volume that will be stored on the host
#
ARG PERSISTENT_VOLUME_DIR="/home/calibre/calibre_volume"
ARG PERSISTENT_VOLUME_GROUP="persistent_volume_group"

RUN addgroup --gid 31382 ${PERSISTENT_VOLUME_GROUP}
RUN useradd -m -G ${PERSISTENT_VOLUME_GROUP} calibre

# Symlink ~/.config into the persisten volume. Note that this directory
# must be created on the host when launching the container!
#
RUN mkdir -p ${PERSISTENT_VOLUME_DIR}/.config \
    && ln -s ${PERSISTENT_VOLUME_DIR}/.config /home/calibre/.config

# Copy all the setup files we'll need during first-time setup of the container
#
ADD setup /home/calibre/setup
RUN chown -R calibre:calibre /home/calibre/setup
USER calibre
WORKDIR /home/calibre

# Install Calibre Plugins
#
RUN calibre-customize --add-plugin=/home/calibre/setup/calibre_resources/DeDRM_Plugin.zip \
 && calibre-customize --add-plugin=/home/calibre/setup/calibre_resources/Obok_plugin.zip

ENV WINEPREFIX ${PERSISTENT_VOLUME_DIR}
ENV WINEARCH win32

ENTRYPOINT [ "/home/calibre/setup/setup.sh" ]
VOLUME [ ${PERSISTENT_VOLUME_DIR} ]