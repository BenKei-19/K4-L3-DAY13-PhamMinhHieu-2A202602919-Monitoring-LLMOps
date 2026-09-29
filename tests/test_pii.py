from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD cua toi la 079203001234")
    assert "079203001234" not in out
    assert out == "CCCD cua toi la [REDACTED_CCCD]"


def test_scrub_credit_card_formats() -> None:
    card_numbers = (
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
    )

    for card_number in card_numbers:
        out = scrub_text(f"Card: {card_number}")
        assert card_number not in out
        # The whole number is one card token, not partially matched as a phone/CCCD.
        assert out == "Card: [REDACTED_CREDIT_CARD]"


def test_scrub_passport() -> None:
    out = scrub_text("Passport C1234567 expires soon")
    assert "C1234567" not in out
    assert "REDACTED_PASSPORT_VN" in out


def test_scrub_multiple_pii_in_one_message() -> None:
    out = scrub_text("Mail a@b.com, phone 0987654321, card 4111 1111 1111 1111")
    assert "a@b.com" not in out
    assert "0987654321" not in out
    assert "4111 1111 1111 1111" not in out


def test_scrub_keeps_non_pii_text() -> None:
    text = "P95 latency was 350 ms over 10 requests"
    assert scrub_text(text) == text
