import pytest

from api.errors import ResponseDecodeError
from api.response import parse_response


def test_json_must_decode_to_object():
    with pytest.raises(ResponseDecodeError):
        parse_response('[{"id": "r1", "status": "ok", "items": []}]')
