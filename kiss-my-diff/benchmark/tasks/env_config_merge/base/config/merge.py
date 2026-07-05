def resolve_config(defaults, env):
    config = dict(defaults)
    for key, value in env.items():
        config[key] = value
    return config
