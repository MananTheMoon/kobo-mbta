ps aux | grep '[p]ython main.py' | awk '{print $1}'
cd /mnt/onboard/.apps/kobo-mbta && python main.py