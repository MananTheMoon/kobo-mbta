from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.dom.minidom import parseString
import requests
from requests.exceptions import RequestException
import time
from typing import List, Literal, Dict, TypedDict
from mbta_static_data import STOPS, ROUTES

StopTypes = Literal["Bus", "Subway", "Rail"]


class StopData(TypedDict):
    type: StopTypes
    name: str


class Prediction(TypedDict):
    arrivalTime: datetime
    departureTime: datetime
    direction: int
    route: str
    icon: str
    type: str


Predictions = Dict[str, List[Prediction]]
Trips = Dict[str, str]


class TransitStop(TypedDict):
    predictions: Predictions
    type: StopTypes
    name: str
    icon: str


MBTA_API_URL = "https://api-v3.mbta.com"
FETCH_LIMIT = 50
DISPLAY_LIMIT = 6


class transit:
    def __init__(self, stops: List[str]):
        self.stops = list(filter(None, stops))
        try:
            res = requests.get(
                f'{MBTA_API_URL}/stops?filter[id]={",".join(self.stops)}'
            )
            if res.status_code != 200:
                raise ValueError("MBTA Request Unsuccessful: \r\n{}".format(res.json()))
            data = res.json()["data"]
            if len(data) != len(self.stops):
                raise ValueError(
                    "One or more stops could not be found: \r\n{}".format(data)
                )
        except RequestException as e:
            raise ValueError("MBTA Request Failed, check stops:\r\n{}".format(e))

    def _get_stop_type(self, stop: str) -> StopTypes:
        if stop in STOPS:
            return STOPS[stop]["type"]
        elif stop.isnumeric():
            return "Bus"
        return "Subway"

    def _get_stop_data(self, stop: str) -> StopTypes:
        default_stop_type = "Bus" if stop.isnumeric() else "Subway"
        return {
            "type": default_stop_type,
            "name": stop,
            **(STOPS[stop] if stop in STOPS else {}),
        }

    def _transform_trips(self, trips_list: List) -> Trips:
        return {obj["id"]: obj["attributes"]["headsign"] for obj in trips_list}

    def _get_stop_icon(self, stop_data: StopData) -> str:
        if "icon" in stop_data:
            return stop_data["icon"]
        if stop_data["type"] == "Bus":
            return "icons-transit/Bus.png"

        if stop_data["type"] == "Subway":
            return "icons-transit/Subway.png"
        return "icons-transit/Train-Bus.png"

    def _get_route_icon(self, route: str):
        if route in ROUTES:
            return ROUTES[route]["icon"]
        if route.isnumeric():
            return ROUTES["Bus"]["icon"]
        return ROUTES["default"]["icon"]

    def _get_route_type(self, route: str):
        if route in ROUTES:
            return ROUTES[route]["type"]
        if route.isnumeric():
            return ROUTES["Bus"]["type"]
        return ROUTES["default"]["type"]

    def _get_predictions(self, stop: str) -> TransitStop:
        for attempt in range(5):
            try:
                print(
                    "URL: ",
                    f"{MBTA_API_URL}/predictions?filter[stop]={stop}&page[limit]={FETCH_LIMIT}&include=trip&sort=departure_time",
                )
                res = requests.get(
                    f"{MBTA_API_URL}/predictions?filter[stop]={stop}&page[limit]={FETCH_LIMIT}&include=trip&sort=departure_time"
                )
                data = res.json()["data"]
                return self._transform_mbta_predictions(
                    data,
                    self._transform_trips(res.json()["included"]),
                    self._get_stop_data(stop),
                )
            except RequestException as e:
                print("MBTA Prediction Request for {stop} failed. \r\n{}".format(e))
                time.sleep(2**attempt)
                continue
        return {}

    def _transform_mbta_predictions(
        self, data: List, trips: Trips, stop_data: StopData
    ) -> Predictions:
        predictions: Predictions = {value: [] for key, value in trips.items()}
        filtered_data = [
            obj for obj in data if obj["attributes"]["departure_time"] != None
        ][0:DISPLAY_LIMIT]
        for obj in filtered_data:
            trip_headsign = trips[obj["relationships"]["trip"]["data"]["id"]]
            route = obj["relationships"]["route"]["data"]["id"]
            predictions[trip_headsign].append(
                {
                    "arrivalTime": obj["attributes"]["arrival_time"],
                    "departureTime": obj["attributes"]["departure_time"],
                    "direction": obj["attributes"]["direction_id"],
                    "route": route,
                    "icon": self._get_route_icon(route),
                    "type": self._get_route_type(route),
                }
            )

        return {
            "name": stop_data["name"],
            "type": stop_data["type"],
            "icon": self._get_stop_icon(stop_data),
            "predictions": predictions,
        }

    def get_predictions(self):
        output = {}
        for stop in self.stops:
            stop_name = STOPS[stop]["name"] if stop in STOPS else stop
            output[stop_name] = self._get_predictions(stop)
        return output


test_cfg = ["2736", "place-davis", "place-balsq"]
if __name__ == "__main__":
    print("Main func")
    x = transit({"stop1": "2736", "stop2": "2737", "stop3": "place-balsq"})
