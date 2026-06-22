def extract_title(text):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Untitled"
