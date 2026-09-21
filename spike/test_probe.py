from probe import mentions_captcha


def test_detects_captcha_markers():
    assert mentions_captcha('<img src="/captcha.jpg">')
    assert mentions_captcha('<div class="g-recaptcha"></div>')
    assert not mentions_captcha("<form><input name='q'></form>")
