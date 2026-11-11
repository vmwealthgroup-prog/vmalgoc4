import pytest
from pydantic import ValidationError

from app.routers.brokers import KotakNeoAccountIn


@pytest.mark.parametrize(
    ("mobile", "expected"),
    [
        ("9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+919876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
    ],
)
def test_kotak_neo_mobile_number_is_normalized(mobile, expected):
    account = KotakNeoAccountIn(
        label="Test account",
        consumer_key="consumer-key-long-enough",
        mobile_number=mobile,
        ucc="TEST123",
    )
    assert account.mobile_number == expected


def test_kotak_neo_rejects_invalid_mobile_number():
    with pytest.raises(ValidationError):
        KotakNeoAccountIn(
            label="Test account",
            consumer_key="consumer-key-long-enough",
            mobile_number="12345",
            ucc="TEST123",
        )
