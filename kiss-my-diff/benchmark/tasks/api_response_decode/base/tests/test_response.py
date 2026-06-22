import pytest

from api.errors import ResponseDecodeError
from api.response import parse_response


def test_valid_response_is_decoded():
    raw = '{"id": "r1", "status": "ok", "items": [1, 2]}'

    assert parse_response(raw) == {"id": "r1", "status": "ok", "items": [1, 2]}


def test_invalid_json_raises_decode_error():
    with pytest.raises(ResponseDecodeError):
        parse_response("{not-json")


def test_missing_id_raises_decode_error():
    with pytest.raises(ResponseDecodeError):
        parse_response('{"status": "ok", "items": []}')


def test_missing_status_raises_decode_error():
    with pytest.raises(ResponseDecodeError):
        parse_response('{"id": "r1", "items": []}')


def test_items_must_be_a_list():
    with pytest.raises(ResponseDecodeError):
        parse_response('{"id": "r1", "status": "ok", "items": "oops"}')


def test_missing_items_raises_decode_error():
    with pytest.raises(ResponseDecodeError):
        parse_response('{"id": "r1", "status": "ok"}')
