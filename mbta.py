from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.dom.minidom import parseString
import requests
from requests.exceptions import RequestException
import time
from typing import List, Literal, Dict
from mbta_static_data import STOPS

StopTypes = Literal["Bus", "Subway", "Rail"]


@dataclass
class StopData:
    type: StopTypes
    name: str


@dataclass
class Prediction:
    arrival_time: datetime
    destination: str


Predictions = Dict[str, List[Prediction]]
Trips = Dict[str, str]


@dataclass
class TransitStop:
    predictions: Predictions
    type: StopTypes
    name: str


MBTA_API_URL = "https://api-v3.mbta.com"


class transit:
    def __init__(self, cfg):
        self.cfg = cfg
        self.stops = list(
            filter(None, [self.cfg["stop1"], self.cfg["stop2"], self.cfg["stop3"]])
        )
        print("Stops: ", self.stops)

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

    def _get_predictions(self, stop: str):
        for attempt in range(5):
            try:
                print(
                    "URL: ",
                    f"{MBTA_API_URL}/predictions?filter[stop]={stop}&page[limit]=6&include=trip&sort=arrival_time",
                )
                res = requests.get(
                    f"{MBTA_API_URL}/predictions?filter[stop]={stop}&page[limit]=6&include=trip&sort=arrival_time"
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
        print("I'm Here??")

    def _transform_mbta_predictions(
        self, data: List, trips: Trips, stop_data: StopData
    ) -> Predictions:
        output = {
            "name": stop_data["name"],
            "type": stop_data["type"],
        }
        predictions = {value: [] for key, value in trips.items()}
        for obj in data:
            trip_headsign = trips[obj["relationships"]["trip"]["data"]["id"]]
            predictions[trip_headsign].append(
                {
                    "arrivalTime": obj["attributes"]["arrival_time"],
                    "direction": obj["attributes"]["direction_id"],
                }
            )

        return {
            "name": stop_data["name"],
            "type": stop_data["type"],
            "predictions": predictions,
        }


test_cfg = {"stop1": "2736", "stop2": "2737", "stop3": "place-balsq"}
if __name__ == "__main__":
    print("Main func")
    x = transit({"stop1": "2736", "stop2": "2737", "stop3": "place-balsq"})
