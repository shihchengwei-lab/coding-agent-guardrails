import hashlib


def stable_bucket(user_id, flag_name):
    digest = hashlib.sha256(f"{flag_name}:{user_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100
