#!/bin/bash
PATH=$PATH:/usr/games:$HOME
CALIBRE_VOLUME="$HOME/calibre_volume"
SETUP_COMPLETED_MARKER="$HOME/.config/SETUP_COMPLETED"

press_any_key () {
    read -n 1 -s -r
}

if [ ! -f "$SETUP_COMPLETED_MARKER" ]; then
    echo "Welcome to 1st-time setup! \
    Please follow all instructions and no one will get hurt.
    Press any key to continue..." | cowsay 
    press_any_key

    # Installing Calibre Plugins
    #
    printf "\n\nInstalling DeDRM Plugin...\n"
    calibre-customize --add-plugin=$HOME/setup/calibre/DeDRM_Plugin.zip

    printf "\n\nInstalling Obok Plugin...\n"
    calibre-customize --add-plugin=$HOME/setup/calibre/Obok_plugin.zip

    # Set the default directory for Calibre library
    #
    cp $HOME/setup/calibre/global.py.json $CALIBRE_VOLUME/.config/calibre/

    printf "\n\n\n"
    echo "Calibre Plugins are installed. \
    Now let's install some Windows stuff...
    A few graphical windows will pop up. It is your duty to ACCEPT ALL DEFAULTS \
    and keep clicking 'Next' until everything is installed.
    Press any key to continue..." | cowsay 
    press_any_key

    # Initialize wine in the home director
    #
    printf "\n\nInitializing Wine Environment...\n"
    cd $CALIBRE_VOLUME
    wineboot
    printf "\n\n\n"

    # Install Python and Crypto
    #
    printf "Installing system utilities...\n\n"
    printf "  >>> ACCEPT DEFAULTS ON EVERYTHING! <<< \n\n"
    cd $HOME/setup/wine
    ./winetricks python27
    wine pycrypto-2.6.win32-py2.7.exe

    printf "\n\n\n"

    # Install Kindle for PC 1.17
    #
    echo "Now we'll install Kindle for PC 1.17.
    At the end of the installation, you'll be prompted for your Amazon credentials. \
    If you have a Kindle, this is an important step to complete. Make sure it \
    works!
    Press any key to continue..." | cowsay
    press_any_key

    printf "\nInstalling Kindle for PC 1.17...\n\n"
    printf "  >>> LOG IN TO YOUR AMAZON ACCOUNT IF YOU HAVE A KINDLE! <<< \n\n"
    cd $HOME/setup/windows
    wine KindleForPC-installer-1.17.44170.exe

    # Write the completion marker
    #
    touch $SETUP_COMPLETED_MARKER

    echo "Tool installation is complete!
    Now you need to configure Calibre DeDRM with information about your Kindle. \
    I am going to open Calibre for you now - please click 'Cancel' on the 1st-time setup screen. 
    Then go to Preferences -> Plugins -> File type plugins -> DeDRM (double-click) -> eInk Kindle ebooks
    Here you need to enter the Serial Number of your Kindle. You can find that on your Kindle, in
        Settings -> Device Options -> Device Info -> Serial Number
        Or on the Amazon website under 'Devices' (https://www.amazon.ca/mn/dcw/myx.html/ref=kinw_myk_redirect)
    The Serial Number needs to be entered without any spaces!
    You should now be able to Add and Convert books you own on your Kindle to any format.
    For more usage instructions, please read the guide: TODO_URL
    Press any key to launch Calibre..." | cowsay 
    press_any_key

    calibre
fi

# Convenience symlinks
#
cd $HOME
ln -s $HOME/setup/windows/kindle.sh kindle
mkdir "$CALIBRE_VOLUME/My Kindle Content" &> /dev/null
ln -s "$CALIBRE_VOLUME/My Kindle Content"

ln -s /usr/bin/calibre

printf "\nTo launch Calibre, type: 'calibre' \n"
printf "To launch Kindle for PC, type: 'kindle' \n"
printf "\n\nInstructions for importing, decrypting and converting books are here:\n"
printf "   TODO_URL\n\n"

/bin/bash
