#!/bin/sh

APP_FOLDER="/mnt/onboard/.apps/yawk/"
INIT_SCRIPT_LOCAL="$APP_FOLDER/utils/init_script"
INIT_SCRIPT_REMOTE="/etc/init.d/yawk"

if [ ! -d $APP_FOLDER ]; then
    echo "Please move the application to the correct folder: $APP_FOLDER"
    exit -1
fi
if [ ! -e "$APP_FOLDER/yawk.py" ]; then
    echo "Please move the application to the correct folder: $APP_FOLDER"
    exit -1
fi
cd $APP_FOLDER

# first, make sure the config.ini exists
if [  -e "config.ini" ]; then
    
	correct='n'
    while [ $correct != 'y' ]; do
        read -p "Enter Stop 1: " stop1
        read -p "Enter Stop 2: " stop2
        read -p "Enter Stop 3: " stop3
        echo
        echo "Your stops are: '$stop1', '$stop2', '$stop3'"
        read -p "Correct? [yn] " correct
    done

    # delete any previous values:
    sed -i '/stop1=/d' config.ini
    sed -i '/stop2=/d' config.ini
    sed -i '/stop3=/d' config.ini

    echo "stop1=$stop1" >> config.ini
    echo "stop2=$stop1" >> config.ini
    echo "stop3=$stop1" >> config.ini
fi
