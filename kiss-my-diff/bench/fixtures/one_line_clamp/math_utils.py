def clamp(value, minimum, maximum):
    if value < minimum:
        return value
    if value > maximum:
        return value
    return value
