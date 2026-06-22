STOPWORDS = {"the", "a", "an", "of"}


def remove_stopwords(words):
    return [word for word in words if word not in STOPWORDS]
