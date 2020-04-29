#!/bin/bash
PATH=$PATH:/usr/games
SETUP_COMPLETED_MARKER="$HOME/.config/SETUP_COMPLETED"

press_any_key () {
    read -n 1 -s -r
}

if [ ! -f "$SETUP_COMPLETED_MARKER" ]; then
    echo "Welcome to 1st-time setup! \
    Please follow all intructions and no one will get hurt. \
    Press any key to continue..." | cowsay 
    press_any_key

    # Installing Calibre Plugins
    #
    printf "\n\nInstalling DeDRM Plugin...\n"
    calibre-customize --add-plugin=$HOME/setup/calibre_resources/DeDRM_Plugin.zip

    printf "\n\nInstalling Obok Plugin...\n"
    calibre-customize --add-plugin=$HOME/setup/calibre_resources/Obok_plugin.zip

    printf "\n\n\n"

    echo "Calibre Plugins are ready to go. \
    Let's install some Windows stuff now. \
    A few graphical windows will pop up. It is your duty to accept all defaults \
    and keep clicking 'Next' until everything is installed.
    Press any key to continue..." | cowsay 
    press_any_key

    # Initialize wine in the home director
    #
    printf "\n\nInitializing Wine Environment...\n"
    cd $HOME/calibre_volume
    wineboot
    printf "\n\n\n"

    # Install Python and Crypto
    #
    printf "Installing system utilities...\n\n"
    printf "  >>> ACCEPT DEFAULTS ON EVERYTHING! <<< \n\n"
    cd $HOME/setup/wine_resources
    wine msiexec /i wine_gecko-2.47-x86.msi
    ./winetricks vcrun2008 python27
    wine pycrypto-2.6.win32-py2.7.exe

    printf "\n\n\n"

    # Install Kindle for PC 1.17
    #
    echo "Now we'll install Kindle for PC 1.17. \
    At the end of the installation, you'll be prompted for your Amazon credentials. \
    If you have a Kindle, this is an important step to complete. Make sure it \
    works! \
    Press any key to continue..." | cowsay 

    printf "\nInstalling Kindle for PC 1.17...\n\n"
    printf "  >>> LOG IN TO YOUR AMAZON ACCOUNT IF YOU HAVE A KINDLE! <<< \n\n"
    cd $HOME/setup/windows_applications
    wine KindleForPC-installer-1.17.44170.exe

    # Write the completion marker
    #
    touch $SETUP_COMPLETED_MARKER

    echo "That's it! \
    Press any key to exit setup and start using this container..." | cowsay 
    press_any_key
fi

cd $HOME
/bin/bash
