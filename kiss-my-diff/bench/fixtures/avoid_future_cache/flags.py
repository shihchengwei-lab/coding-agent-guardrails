DEFAULT_FLAGS = {
    "new_nav": False,
    "fast_checkout": False,
}


def is_enabled(flags, name):
    return flags[name]
