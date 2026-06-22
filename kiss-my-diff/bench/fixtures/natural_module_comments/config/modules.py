def enabled_modules(text):
    return [line.strip() for line in text.splitlines() if line.strip()]
