import time
from datetime import datetime
from subprocess import call
import socket
from sys import platform
import os
from src.app import App

try:
    from _fbink import ffi, lib as fbink
except ImportError:
    from fbink_mock import ffi, lib as fbink


def wait_for_wifi():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_addr = s.getsockname()[0]
            print("Connected, with the IP address: " + ip_addr)
            return ip_addr
        except Exception as e:
            print("exc. ignored {}".format(e))
            os.system("reboot")
        time.sleep(15)


def main():
    print("T-Weather started!")

    if "linux" in platform:
        call(["hostname", "kobo"])

    wait_for_wifi()

    if "linux" in platform:
        call(["killall", "-TERM", "nickel", "hindenburg", "sickel", "fickel"])

    app = App()
    counter = 0

    try:
        while True:
            print(
                "*** Updating at "
                + datetime.now().strftime("%d.%m.%y, %Hh%M")
                + " (update nr. "
                + str(counter)
                + ") ***"
            )
            app.ip_address = wait_for_wifi()
            app.update()
            print("Sleeping")
            # sleep 1 min, but ping every 30 seconds... maybe the wifi will stay on
            for sleep in range(2):
                time.sleep(30)
                os.system("ping -c 1 -q www.google.com > /dev/null")
            counter += 1
    finally:
        fbink.fbink_close(app.fbfd)


if __name__ == "__main__":
    main()
