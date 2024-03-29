from cgitb import small
import configparser
from dataclasses import dataclass
from operator import ne
from typing import List
import socket
import tempfile
import time
from datetime import datetime
from subprocess import call
from sys import platform
import os
from xml.etree.ElementInclude import include
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont
from PIL.Image import Image as PilImage
from weather import weather_current, weather_forecast, yawkWeather
from mbta import transit, Prediction

try:
    from _fbink import ffi, lib as fbink
except ImportError:
    from fbink_mock import ffi, lib as fbink

CONFIGFILE = "config.ini"

white = 255
black = 0
gray = 128


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


def get_config_data(file_path):
    """turns the config file data into a dictionary"""
    parser = configparser.RawConfigParser()
    parser.read(file_path)
    data = dict()
    data["api_key"] = parser.get("yawk", "key")
    data["city_id"] = parser.get("yawk", "city")
    data["stop_1"] = parser.get("yawk", "stop1")
    data["stop_2"] = parser.get("yawk", "stop2")
    data["stop_3"] = parser.get("yawk", "stop3")

    print("api: {}\ncity: {}".format(data["api_key"], data["city_id"]))

    return data


@dataclass
class box_descriptor:
    pos_x: int
    pos_y: int
    width: int
    height: int


@dataclass
class boxes:
    current: box_descriptor
    today: box_descriptor
    mbta_1: box_descriptor
    mbta_2: box_descriptor
    mbta_3: box_descriptor
    # tomorrow: box_descriptor
    # next_days: List[box_descriptor]


@dataclass
class fonts:
    xtiny: FreeTypeFont
    tiny: FreeTypeFont
    small: FreeTypeFont
    comfort: FreeTypeFont
    big: FreeTypeFont


@dataclass
class icons:
    wind: PilImage
    humidity: PilImage
    temperature: PilImage


@dataclass
class data:
    current: weather_current
    forecast: List[weather_forecast]


class YAWK:
    # BORDER, in pixels, so we don't draw too close to the edges
    BORDER = 10

    def __init__(self):
        # config from the file
        self.cfg_data = dict()
        cfg_file_data = get_config_data(CONFIGFILE)
        self.cfg_data["api"] = cfg_file_data["api_key"]
        self.cfg_data["city"] = cfg_file_data["city_id"]
        self.cfg_data["stops"] = [
            cfg_file_data["stop_1"],
            cfg_file_data["stop_2"],
            cfg_file_data["stop_3"],
        ]

        # fbink configuration
        self.fbink_cfg = ffi.new("FBInkConfig *")
        self.fbink_cfg.is_centered = True
        self.fbink_cfg.is_halfway = True
        self.fbink_cfg.is_cleared = True

        self.fbfd = fbink.fbink_open()
        fbink.fbink_init(self.fbfd, self.fbink_cfg)
        state = ffi.new("FBInkState *")
        fbink.fbink_get_state(self.fbink_cfg, state)

        if "linux" in platform:
            self.screen_size = (state.view_width, state.view_height)
        else:
            self.screen_size = (768, 1024)

        # 758 x 1024
        self.WIDTH = int(self.screen_size[0])
        self.HEIGHT = int(self.screen_size[1])

        # app configuration
        self.ip_address = "1.1.1.1"

        # weather class instance
        try:
            print("Getting weather data...")
            self.weather_fetcher = yawkWeather(self.cfg_data)
            self.weather = data(
                current=self.weather_fetcher.get_weather_current(),
                forecast=self.weather_fetcher.get_weather_forecast(),
            )
            print("Successfully fetched weather data.")
        except Exception as e:
            print("ERROR: Fetching weather data failed.\n", e)
            fbink.fbink_close(self.fbfd)

        try:
            print("Getting transit Data...")
            self.transit_data = transit(self.cfg_data["stops"]).get_predictions()
            print("\nTransit Data:\n\n", self.transit_data)
        except Exception as e:
            print("ERROR: Fetching weather data failed.\n", e)
            fbink.fbink_close(self.fbfd)

        # configuration for the image
        # Boxes positions
        #   current condition
        current = box_descriptor(
            0, 0, int(2 * self.screen_size[0] / 3), int(self.screen_size[1] / 3)
        )
        #   today's forecast
        today = box_descriptor(
            current.width, 0, self.screen_size[0] - current.width, current.height
        )

        mbta_1 = box_descriptor(
            0,
            current.height,
            self.screen_size[0],
            int((self.screen_size[1] - current.height) / 3),
        )

        mbta_2 = box_descriptor(
            0,
            current.height + mbta_1.height,
            self.screen_size[0],
            int((self.screen_size[1] - current.height) / 3),
        )

        mbta_3 = box_descriptor(
            0,
            current.height + mbta_1.height + mbta_2.height,
            self.screen_size[0],
            int((self.screen_size[1] - current.height) / 3),
        )

        #   tomorrow
        tomorrow = box_descriptor(
            0,
            current.height,
            self.screen_size[0],
            int((self.screen_size[1] - current.height) / 3),
        )

        self.boxes = boxes(current, today, mbta_1, mbta_2, mbta_3)
        # fonts
        #   tiny: used on the weather condition for the next days and ip address
        #   small: used on the headers and most stuff on the current conditions
        #   comfort: temperatures (gets scaled according to the box)
        #   big: for the current temperature
        self.fonts = fonts(
            xtiny=ImageFont.truetype("fonts/Cabin-Regular.ttf", 18),
            tiny=ImageFont.truetype("fonts/Cabin-Regular.ttf", 22),
            small=ImageFont.truetype("fonts/Fabrica.otf", 26),
            comfort=ImageFont.truetype("fonts/Comfortaa-Regular.ttf", 60),
            big=ImageFont.truetype(
                "fonts/Comfortaa-Regular.ttf", int(self.screen_size[1] / 10)
            ),
        )

        # icons
        self.icons = icons(
            wind=Image.open("icons/w.png"),
            humidity=Image.open("icons/h.png"),
            temperature=Image.open("icons/deg_f.png"),
        )

    def _create_image(self) -> str:
        print("Creating image . . .")
        today = self.weather.forecast[0]

        img = Image.new("L", (self.WIDTH, self.HEIGHT), color=white)
        draw = ImageDraw.Draw(img, "L")

        # Dividing lines
        # under today/current
        draw.line(
            [
                (self.BORDER, self.boxes.current.height),
                (self.WIDTH - self.BORDER, self.boxes.current.height),
            ],
            gray,
        )
        # between today/current
        draw.line(
            [
                (self.boxes.current.width, self.BORDER),
                (self.boxes.current.width, self.boxes.current.height - self.BORDER),
            ],
            gray,
        )
        # under mbta_1
        draw.line(
            [
                (self.BORDER, self.boxes.mbta_2.pos_y),
                (self.WIDTH - self.BORDER, self.boxes.mbta_2.pos_y),
            ],
            gray,
        )
        # under mbta_2
        draw.line(
            [
                (self.BORDER, self.boxes.mbta_3.pos_y),
                (self.WIDTH - self.BORDER, self.boxes.mbta_3.pos_y),
            ],
            gray,
        )

        # Draw Transit Stuff
        transit_boxes: List[box_descriptor] = [
            self.boxes.mbta_1,
            self.boxes.mbta_2,
            self.boxes.mbta_3,
        ]
        for i, (key, value) in enumerate(self.transit_data.items()):
            self._draw_transit_data(img, draw, transit_boxes[i], value)

        # Current conditions
        # City Name, Country Code, Day, Time
        header = (
            self.weather.current.city.split(",")[0]
            + ", "
            + datetime.now()
            .astimezone(ZoneInfo("America/New_York"))
            .strftime("%Y-%m-%d %H:%M")
        )
        header_w, header_h = draw.textsize(header, font=self.fonts.small)
        draw.text(
            (self.boxes.current.width / 2 - header_w / 2, self.BORDER),
            header,
            font=self.fonts.small,
            fill=black,
        )
        # temperature

        temp_w, temp_h = draw.textsize(
            str(round(self.weather.current.temperature)), font=self.fonts.big
        )
        draw.text(
            (self.BORDER * 3, 2 * self.boxes.current.height / 7),
            str(round(self.weather.current.temperature)),
            font=self.fonts.big,
            fill=black,
        )
        # farenheit
        img.paste(
            self.icons.temperature.resize((32, 32)),
            (self.BORDER * 3 + temp_w, int(2 * self.boxes.current.height / 7) - 10),
        )
        # condition icon
        condition = Image.open(self.weather.current.icon)
        condition = condition.resize(
            (int(condition.size[0] * 1.2), int(condition.size[1] * 1.2))
        )
        temp_end_x = self.BORDER * 3 + temp_w + 32
        x = int((self.boxes.current.width + temp_end_x) / 2 - condition.size[0] / 2)
        img.paste(
            condition, (x, int(self.boxes.current.height / 2 - condition.size[1] / 2))
        )
        # condition description - under the icon?
        condition_w, condition_h = draw.textsize(
            self.weather.current.condition, font=self.fonts.small
        )
        x = (self.boxes.current.width + temp_end_x) / 2 - condition_w / 2
        y = self.boxes.current.height / 2 + int(condition.size[1] / 2) + 3 * self.BORDER
        draw.text(
            (x, y), self.weather.current.condition, font=self.fonts.small, fill=gray
        )
        # wind icon
        y = self.boxes.current.height - self.icons.wind.size[1]
        img.paste(self.icons.wind, (self.BORDER, y))
        # wind value
        wind_w, wind_h = draw.textsize(
            str(int(round(self.weather.current.wind, 0))) + "km/h",
            font=self.fonts.small,
        )
        y = y + self.icons.wind.size[1] / 2 - wind_h / 2
        draw.text(
            (self.BORDER + self.icons.wind.size[0] + self.BORDER, y),
            str(int(round(self.weather.current.wind, 0))) + "km/h",
            font=self.fonts.small,
            fill=black,
        )
        # humidity icon
        y = (
            self.boxes.current.height
            - self.icons.wind.size[1]
            - self.icons.humidity.size[1]
        )
        x = int(
            self.BORDER + self.icons.wind.size[0] / 2 - self.icons.humidity.size[0] / 2
        )
        img.paste(self.icons.humidity, (x, y))
        # humidity value
        humidity_w, humidity_h = draw.textsize(
            str(int(round(self.weather.current.humidity, 0))) + "%",
            font=self.fonts.small,
        )
        y = y + self.icons.humidity.size[1] / 2 - humidity_h / 2
        draw.text(
            (self.BORDER + self.icons.wind.size[0] + self.BORDER, y),
            str(int(round(self.weather.current.humidity, 0))) + "%",
            font=self.fonts.small,
            fill=black,
        )

        def print_temp(pos: int, text: str, temp: float, scale: float = 1.0):
            # text string
            text_w, text_h = draw.textsize(text, font=self.fonts.small)
            y = pos[1] - text_h
            x = pos[0]
            draw.text((x, y), text, font=self.fonts.small, fill=gray)
            # value
            temp_width, temp_height = draw.textsize(
                str(round(temp)), font=self.fonts.comfort
            )
            y = y + text_h - temp_height
            x += text_w
            draw.text((x, y), str(round(temp)), font=self.fonts.comfort, fill=black)
            # farenheit
            x += temp_width
            img.paste(
                self.icons.temperature.resize(
                    (
                        int(32 * scale),
                        int(32 * scale),
                    )
                ),
                (int(x), int(y) - 10),
            )

        # today's forecast
        # low temperature
        position = [self.boxes.today.pos_x + self.BORDER, self.boxes.today.height / 4]
        print_temp(position, "low: ", today.low, 1.3)
        # high temperature
        position = [
            self.boxes.today.pos_x + self.BORDER,
            2 * self.boxes.today.height / 4,
        ]
        print_temp(position, "high: ", today.high, 1.3)
        # condition icon
        condition = Image.open(today.icon)
        y = int(3 * self.boxes.today.height / 4 - condition.size[1] / 2)
        x = int(
            self.boxes.today.pos_x + self.boxes.today.width / 2 - condition.size[0] / 2
        )
        img.paste(condition, (x, y))

        # ip address
        ip_w, ip_h = draw.textsize(self.ip_address, font=self.fonts.tiny)
        draw.text(
            (self.WIDTH - self.BORDER - ip_w, self.HEIGHT - self.BORDER - ip_h),
            self.ip_address,
            font=self.fonts.tiny,
            fill=gray,
        )

        # battery level
        if "linux" in platform:
            bat_percent = 0
            with open("/sys/class/power_supply/mc13892_bat/capacity") as file:
                bat_percent = file.readline()
                bat_percent = bat_percent.rstrip("\n")
            bat_w, bat_h = draw.textsize(bat_percent + "%", font=self.fonts.tiny)
            draw.text(
                (self.BORDER, self.HEIGHT - self.BORDER - bat_h),
                bat_percent + "%",
                font=self.fonts.tiny,
                fill=gray,
            )

        if "linux" in platform:
            img.save(tempfile.gettempdir() + "/img.bmp")
            return bytes(tempfile.gettempdir() + "/img.bmp", "utf-8")
        else:
            img.save(tempfile.gettempdir() + "\\img.bmp")
            return bytes(tempfile.gettempdir() + "\\img.bmp", "utf-8")

    def _draw_transit_data(
        self, img: Image.Image, draw: ImageDraw.ImageDraw, box: box_descriptor, data
    ):
        spacer = 10
        box_left = box.pos_x + self.BORDER
        box_top = box.pos_y + self.BORDER
        print("Should draw transit data here")
        cursor_y = box_top
        cursor_x = box_left + spacer

        title_height = 32
        footer_height = 64

        # Title Row
        subway_icon = Image.open(data["icon"]).resize((32, 32))
        print("MBTA Box 1 (X,Y): ", self.boxes.mbta_1.pos_x, box.pos_y)
        print("MBTA Box 2 (X,Y): ", self.boxes.mbta_2.pos_x, box.pos_y)
        img.paste(subway_icon, (cursor_x, cursor_y))
        cursor_x += subway_icon.width + spacer
        draw.text(
            xy=(cursor_x, cursor_y + 5),
            text=data["name"],
            font=self.fonts.small,
            fill=black,
        )
        cursor_x = box_left
        cursor_y += title_height + spacer

        # Prediction Box
        prediction_width = (self.WIDTH - 2 * self.BORDER) / 6  # 6 predictions per row
        prediction_height = box.height - 2 * spacer - title_height - footer_height
        prediction_box = box_descriptor(
            cursor_x, cursor_y, prediction_width, prediction_height
        )
        current_time = datetime.now()

        for destination, predictions in data["predictions"].items():
            if predictions:
                predictions_drawn = 0
                cursor_x_start = cursor_x
                for prediction in predictions:
                    self._draw_single_prediction(
                        img=img,
                        draw=draw,
                        box=prediction_box,
                        prediction=prediction,
                        current_time=current_time,
                    )
                    cursor_x += prediction_box.width
                    prediction_box.pos_x = prediction_box.pos_x + prediction_box.width
                    predictions_drawn += 1

                center_of_prediction_set = (cursor_x + cursor_x_start) / 2
                self._draw_centered_text(
                    draw=draw,
                    xy=(
                        center_of_prediction_set,
                        cursor_y + prediction_box.height + spacer,
                    ),
                    text=destination.split(" ")[0],
                    font=self.fonts.xtiny,
                    fill=black,
                )
                draw.line(
                    [
                        (cursor_x, cursor_y),
                        (cursor_x, cursor_y + prediction_box.height + footer_height),
                    ],
                    gray,
                )

    def _draw_centered_text(
        self, draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill
    ):
        x, y = xy
        size_x, size_y = draw.textsize(text=text, font=font)
        draw.text(xy=(int(x - size_x / 2), int(y)), text=text, font=font, fill=fill)

    def _draw_single_prediction(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        box: box_descriptor,
        prediction: Prediction,
        current_time,
    ) -> tuple[int, int]:
        # Draw a prediction and return the size of the box drawn
        spacer = 10
        cursor_y = box.pos_y
        middle_x = box.pos_x + box.width / 2
        departure = datetime.strptime(
            prediction["departureTime"][:-6], "%Y-%m-%dT%H:%M:%S"
        )
        time_left = max(((departure - current_time).seconds - 30) / 60, 0)
        icon = Image.open(prediction["icon"]).resize((32, 32))

        img.paste(icon, (int(middle_x - icon.width / 2), cursor_y))
        cursor_y += icon.height + spacer

        self._draw_centered_text(
            draw,
            (middle_x, cursor_y),
            text=f"{int(time_left)}m",
            font=self.fonts.small,
            fill=black,
        )

    def update(self):
        try:
            self.weather.current = self.weather_fetcher.get_weather_current()
            self.weather.forecast = self.weather_fetcher.get_weather_forecast()
        except Exception as e:
            # Something went wrong while getting API Data, try again later.
            print("Failed to get weather data:\r\n" + str(e))
            return
        image = self._create_image()
        print("Drawing image")
        rect = ffi.new("FBInkRect *")
        rect.top = 0
        rect.left = 0
        rect.width = 0
        rect.height = 0
        if "linux" in platform:
            fbink_version = ffi.string(fbink.fbink_version()).decode("ascii")
            fbink_version: str
            fbink_version = fbink_version.split(" ")[0]
            fbink_version = fbink_version.split("v")[1]
            major = fbink_version.split(".")[0]
            minor = fbink_version.split(".")[1]
            fbink_version = int(major) * 100 + int(minor)
            if fbink_version >= 124:
                fbink.fbink_cls(self.fbfd, self.fbink_cfg, rect, 0)
            else:
                fbink.fbink_cls(self.fbfd, self.fbink_cfg, rect)

        fbink.fbink_print_image(self.fbfd, image, 0, 0, self.fbink_cfg)


def main():
    print("YAWK started!")

    if "linux" in platform:
        call(["hostname", "kobo"])

    wait_for_wifi()

    if "linux" in platform:
        call(["killall", "-TERM", "nickel", "hindenburg", "sickel", "fickel"])

    yawk = YAWK()
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
            yawk.ip_address = wait_for_wifi()
            yawk.update()
            print("Sleeping")
            # sleep 5 min, but ping every 30 seconds... maybe the wifi will stay on
            for sleep in range(10):
                time.sleep(30)
                os.system("ping -c 1 -q www.google.com > /dev/null")
            counter += 1
    finally:
        fbink.fbink_close(yawk.fbfd)


if __name__ == "__main__":
    main()
