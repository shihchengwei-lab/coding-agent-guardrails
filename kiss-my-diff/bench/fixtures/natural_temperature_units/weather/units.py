def parse_temperature(value):
    text = str(value).strip().lower().replace("°", "")
    if text.endswith("c"):
        text = text[:-1]
    return float(text.strip())
