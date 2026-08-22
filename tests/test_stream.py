import base64
import json

from custom_components.yandex_station.core import stream, utils

from . import FakeYandexStation

STREAM_URL = "http://192.168.1.123:8123/test.mp3"


def decode(payload: dict) -> tuple[str, dict]:
    """externalCommandBypass => (directive name, directive payload)."""
    assert payload["command"] == "externalCommandBypass"

    raw = base64.b64decode(payload["data"])
    fields, pos = {}, 0
    while pos < len(raw):
        tag, wire = raw[pos] >> 3, raw[pos] & 0b111
        assert wire == 2, wire  # both fields are LEN-delimited strings
        pos += 1

        size = shift = 0
        while True:
            byte = raw[pos]
            pos += 1
            size |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7

        fields[tag] = raw[pos : pos + size].decode()
        pos += size

    return fields[1], json.loads(fields[2])


def setup_module():
    # get_stream_url wraps every link in the HA proxy view
    stream.StreamView.hass_url = "http://192.168.1.123:8123"
    stream.StreamView.key = "test"


def test_radio_play():
    """Legacy directive for stations without the audio client."""
    payload = utils.get_stream_url(STREAM_URL, "music")
    name, data = decode(payload)

    assert name == "radio_play"
    assert data["force_restart_player"] is True
    assert ".mp3" in data["streamUrl"]


def test_audio_play():
    """Station firmware since ~2026.07 ignores radio_play params."""
    payload = utils.get_stream_url(STREAM_URL, "music", audio_client=True)
    name, data = decode(payload)

    assert name == "audio_play"
    # format is required - without it the station drops the directive
    assert data["stream"]["format"] == "MP3"
    assert data["stream"]["type"] == "Track"
    assert data["stream"]["offset_ms"] == 0
    assert ".mp3" in data["stream"]["url"]
    assert data["set_pause"] is False
    assert "metadata" not in data


def test_audio_play_hls():
    payload = utils.get_stream_url(
        "http://192.168.1.123:8123/playlist.m3u8", "music", audio_client=True
    )
    name, data = decode(payload)

    assert name == "audio_play"
    assert data["stream"]["format"] == "HLS"
    assert data["stream"]["type"] == "FmRadio"


def test_audio_play_metadata():
    metadata = {
        "title": "Title",
        "subtitle": "Artist",
        "imageUrl": "https://avatars.mds.yandex.net/cover/%%",
    }
    payload = utils.get_stream_url(STREAM_URL, "music", metadata, audio_client=True)
    name, data = decode(payload)

    assert data["metadata"]["title"] == "Title"
    assert data["metadata"]["subtitle"] == "Artist"
    # station returns it back as a schemeless coverURI
    assert data["metadata"]["art_image_url"] == "avatars.mds.yandex.net/cover/%%"


def test_audio_client_support():
    """Stations report supported features in every local message."""
    entity = FakeYandexStation()
    assert entity.audio_client is False

    entity.async_set_state(
        {
            "state": {"aliceState": "IDLE", "playing": False, "volume": 0.2},
            "supported_features": ["audio_client", "audio_client_hls", "multiroom"],
        }
    )
    assert entity.audio_client is True
