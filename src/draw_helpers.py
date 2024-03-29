def middle(a, b):
    return int((a + b) / 2)


def middle_xy(xy1: tuple[float, float], xy2: tuple[float, float]):
    x1, y1 = xy1
    x2, y2 = xy2
    return (middle(x1, x2), middle(y1, y2))
