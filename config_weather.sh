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

# first, check if the config.ini exists
if [  -e "config.ini" ]; then
    # let's create it
	correct='n'
    while [ $correct != 'y' ]; do
        read -p "Enter your API key: " api
        read -p "Enter your city\'s ID: " city
        echo
        echo "Your API key is '$api'"
        echo "Your city ID is '$city'"
        read -p "Correct? [yn] " correct
    done

    sed -i '/key=/d' config.ini
    sed -i '/city=/d' config.ini

    echo "key=$api" >> config.ini
    echo "city=$city" >> config.ini
fi
