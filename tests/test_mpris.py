"""Tests for Linux MPRIS metadata parsing."""

from scout.integrations.mpris import parse_dbus_metadata


def test_parse_dbus_metadata():
    sample_dbus_output = """
    method return time=1787771784.147964 sender=:1.808 -> destination=:1.968 serial=350 reply_serial=2
       variant       array [
             dict entry(
                string "mpris:artUrl"
                variant                string "http://localhost:4533/rest/getCoverArt.view?id=q79CSLo6HfQbSYmrL8PBUF"
             )
             dict entry(
                string "xesam:album"
                variant                string "Underdog"
             )
             dict entry(
                string "xesam:artist"
                variant                array [
                      string "Eve"
                   ]
             )
             dict entry(
                string "xesam:title"
                variant                string "Underdog"
             )
          ]
    """
    metadata = parse_dbus_metadata(sample_dbus_output)
    assert metadata.get("title") == "Underdog"
    assert metadata.get("artist") == "Eve"
    assert metadata.get("album") == "Underdog"
    assert "getCoverArt.view" in metadata.get("artUrl", "")
