import pytest

from app.core.errors import ValidationFailed
from app.services.importer import RowInvalid, normalize_domain, parse_csv, validate_row


def test_normalizes_email_and_domain() -> None:
    row = validate_row({"email": "  Jane.Doe@Acme.COM ", "company_domain": "WWW.Acme.com"})
    assert row.email == "jane.doe@acme.com"
    assert row.domain == "acme.com"
    assert row.first_name is None


def test_optional_fields_are_trimmed_and_blank_becomes_none() -> None:
    row = validate_row(
        {"email": "a@b.co", "company_domain": "b.co", "first_name": " Al ", "job_title": "  "}
    )
    assert row.first_name == "Al"
    assert row.job_title is None


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ({"company_domain": "acme.com"}, "email is required"),
        ({"email": "", "company_domain": "acme.com"}, "email is required"),
        ({"email": "a@b.co"}, "company_domain is required"),
        ({"email": "nope", "company_domain": "acme.com"}, "invalid email"),
        ({"email": "a@b", "company_domain": "acme.com"}, "invalid email"),
        ({"email": "a@b.co", "company_domain": "not a domain"}, "invalid company_domain"),
        ({"email": "a@b.co", "company_domain": "localhost"}, "invalid company_domain"),
        ({"email": 5, "company_domain": "acme.com"}, "email must be a string"),
        ({"email": "a@b.co", "company_domain": "acme.com", "job_title": "x" * 300}, "longer than"),
    ],
)
def test_invalid_rows_give_a_reason(raw: dict[str, object], reason: str) -> None:
    with pytest.raises(RowInvalid, match=reason):
        validate_row(raw)


def test_normalize_domain_only_strips_leading_www() -> None:
    assert normalize_domain("www.example.com") == "example.com"
    assert normalize_domain("awww.example.com") == "awww.example.com"


def test_parse_csv_reads_rows_and_normalizes_headers() -> None:
    rows = parse_csv(b"\xef\xbb\xbf Email ,Company_Domain\na@b.co,b.co\n")
    assert rows == [{"email": "a@b.co", "company_domain": "b.co"}]


def test_parse_csv_missing_required_column() -> None:
    with pytest.raises(ValidationFailed, match="company_domain"):
        parse_csv(b"email,first_name\na@b.co,A\n")


def test_parse_csv_empty_and_bad_encoding() -> None:
    with pytest.raises(ValidationFailed, match="empty"):
        parse_csv(b"")
    with pytest.raises(ValidationFailed, match="UTF-8"):
        parse_csv(b"\xff\xfe\x00bad")


def test_parse_csv_keeps_short_and_long_rows_for_validation() -> None:
    rows = parse_csv(b"email,company_domain\na@b.co\nc@d.co,d.co,extra\n")
    assert rows[0]["company_domain"] is None
    assert rows[1]["_extra_cells"] == ["extra"]
