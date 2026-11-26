import random

import pytest

from jt.engine.redaction import REDACTION_VERSION, ConversationRedactor


@pytest.mark.parametrize(
    ("text", "sensitive_text", "expected"),
    [
        ("我叫顾演宁，请帮忙。", "顾演宁", "我叫<NAME_1>，请帮忙。"),
        ("我叫顾演宁我被困住了。", "顾演宁", "我叫<NAME_1>我被困住了。"),
        ("我的姓名是陆示禾。我迷路了。", "陆示禾", "我的姓名是<NAME_1>。我迷路了。"),
        ("My name is Élia O’Quill and I need help.", "Élia O’Quill",
         "My name is <NAME_1> and I need help."),
        ("Guest name: mira quill", "mira quill", "Guest name: <NAME_1>"),
        ("护照号码是：XZ0000015。", "XZ0000015", "护照号码是：<PASSPORT_1>。"),
        ("护照编号：XZ0000015。", "XZ0000015", "护照编号：<PASSPORT_1>。"),
        ("護照號碼：XZ0000015。", "XZ0000015", "護照號碼：<PASSPORT_1>。"),
        ("Passport No. is XZ0000026.", "XZ0000026", "Passport No. is <PASSPORT_1>."),
        ("Passport #: 000000123", "000000123", "Passport #: <PASSPORT_1>"),
        ("电话：＋８６ １３８ ００００ ００００。", "＋８６ １３８ ００００ ００００",
         "电话：<PHONE_1>。"),
        ("请拨138 0000 0000。", "138 0000 0000", "请拨<PHONE_1>。"),
        ("請回電(010) 5555-0147。", "(010) 5555-0147", "請回電<PHONE_1>。"),
        ("Reach me at +1 (202) 555-0147.", "+1 (202) 555-0147", "Reach me at <PHONE_1>."),
        ("Mobile: +44 7700 900123", "+44 7700 900123", "Mobile: <PHONE_1>"),
        ("邮箱是sample+trip@example.invalid，请发消息。", "sample+trip@example.invalid",
         "邮箱是<EMAIL_1>，请发消息。"),
        ("Email: example.test@example.invalid.", "example.test@example.invalid",
         "Email: <EMAIL_1>."),
        ("我在虚构东路17号2栋305室。", "虚构东路17号2栋305室", "我在<LOCATION_1>。"),
        ("地址：虚构东路17号A座305室。", "虚构东路17号A座305室", "地址：<LOCATION_1>。"),
        ("我在客房 305。", "客房 305", "我在<LOCATION_1>。"),
        ("My address is 17 Example Road, Apt 4B.", "17 Example Road, Apt 4B",
         "My address is <LOCATION_1>."),
        ("I'm in Room 305.", "Room 305", "I'm in <LOCATION_1>."),
        ("定位：22.12345，113.67890。", "22.12345，113.67890",
         "定位：<LOCATION_1>。"),
        ("GPS: -32.12345, 125.67890.", "-32.12345, 125.67890",
         "GPS: <LOCATION_1>."),
        ("GPS: 125.67890,-32.12345.", "125.67890,-32.12345",
         "GPS: <LOCATION_1>."),
    ],
)
def test_redacts_identifiers_in_synthetic_messages(text, sensitive_text, expected):
    result = ConversationRedactor().redact(text)
    assert result == expected
    assert sensitive_text not in result


@pytest.mark.parametrize(
    "text",
    [
        "我叫了一辆车；姓名栏留空。", "My name is not on the reservation.",
        "Guest name: N/A. Full name: none.",
        "护照将在明年到期。航班 CA1234，订单 XZ0000015。",
        "I lost my passport. The sample order code is XZ0000026.",
        "请拨 110、119 或 120。航班号是 CA1234。",
        "Call 110 or 120. My ETA is 20:10 and the price is +120 CNY.",
        "邮箱格式：name@local。", "Use the email field shown as name@example.",
        "17号线到虚构东路。下一站是样例广场。", "Meet near Example Road in Guangzhou.",
        "时间是 22:30；区间 110–120。", "Price ranges are 22.10, 113.20.",
    ],
)
def test_preserves_similar_non_identifiers(text):
    assert ConversationRedactor().redact(text) == text


def test_numbering_is_stable_and_local_to_a_conversation():
    first = ConversationRedactor()
    second = ConversationRedactor()

    assert first.redact("My name is Mira Quill. Mira Quill is on the form.") == (
        "My name is <NAME_1>. <NAME_1> is on the form."
    )
    assert first.redact("姓名：陆示禾；护照号：XZ0000037。") == (
        "姓名：<NAME_2>；护照号：<PASSPORT_1>。"
    )
    assert first.redact("MIRA QUILL / 陆示禾 / xz0000037") == "<NAME_1> / <NAME_2> / <PASSPORT_1>"
    assert second.redact("Mira Quill / 陆示禾 / XZ0000037") == "Mira Quill / 陆示禾 / XZ0000037"
    assert second.redact("姓名：陆示禾。") == "姓名：<NAME_1>。"


def test_numbers_and_emails_reuse_placeholders_across_formatting():
    redactor = ConversationRedactor()
    assert redactor.redact(
        "+1 (202) 555-0147, sample@example.invalid, 202-555-0199, other@example.invalid"
    ) == "<PHONE_1>, <EMAIL_1>, <PHONE_2>, <EMAIL_2>"
    assert redactor.redact("＋１２０２５５５０１４７，SAMPLE@example.invalid") == "<PHONE_1>，<EMAIL_1>"


def test_overlap_never_exposes_the_rest_of_an_identifier():
    redactor = ConversationRedactor()
    assert redactor.redact("Name: Mira") == "Name: <NAME_1>"
    assert redactor.redact("Guest name: Mira@example.invalid; passport: 2025550147.") == (
        "Guest name: <EMAIL_1>; passport: <PASSPORT_1>."
    )


def test_coordinates_reuse_placeholders_across_separators():
    redactor = ConversationRedactor()
    assert redactor.redact("定位：22.12345，113.67890。") == "定位：<LOCATION_1>。"
    assert redactor.redact("GPS: 22.12345, 113.67890") == "GPS: <LOCATION_1>"


def test_existing_placeholder_is_never_replaced_by_a_matching_name():
    redactor = ConversationRedactor()
    result = redactor.redact("姓名：Location。Room 305.")
    assert result == "姓名：<NAME_1>。<LOCATION_1>."
    assert redactor.redact(result) == result


def test_types_and_redaction_version_are_stable_on_mixed_synthetic_input():
    assert REDACTION_VERSION == "1"
    fields = [
        ("我叫顾演宁。", "我叫<NAME_1>。"),
        ("Passport: XZ0000015", "Passport: <PASSPORT_1>"),
        ("电话：138 0000 0000", "电话：<PHONE_1>"),
        ("sample@example.invalid", "<EMAIL_1>"),
        ("我在 Example Plaza 的房间 305。", "我在 Example Plaza 的<LOCATION_1>。"),
        ("原标记 <NAME_8>。", "原标记 <NAME_8>。"),
    ]
    random.Random(1709).shuffle(fields)
    text, expected = zip(*fields)
    redactor = ConversationRedactor()
    result = redactor.redact("\n".join(text))
    assert result == "\n".join(expected)
    assert redactor.redact(result) == result
