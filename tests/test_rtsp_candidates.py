from app.services.rtsp_probe import vendor_candidates


def test_vendor_candidates_include_known_patterns():
    xs=vendor_candidates("192.168.1.49","admin","secret")
    assert any("/av0_0" in x for x in xs)
    assert any("/av0_1" in x for x in xs)
    assert any("/video" in x for x in xs)
    assert any("/subvideo" in x for x in xs)
    assert any("user=admin" in x and "password=secret" in x for x in xs)
