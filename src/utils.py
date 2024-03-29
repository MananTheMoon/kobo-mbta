from datetime import datetime


def to_datetime(time_str: str, format="%Y-%m-%dT%H:%M:%S", strip_timezone=True):
    time_str = time_str[:-6] if strip_timezone else time_str
    return datetime.strptime(time_str, format)
