"""Unit tests for the P1 normalizers: phone, date, country (architecture s6).

Each is a pure, total function returning a NormResult: a value + norm_quality,
or an abstention. Never a guess.
"""

from transformer.normalize.country import normalize_country
from transformer.normalize.date import normalize_date
from transformer.normalize.phone import normalize_phone
from transformer.normalize.result import NormContext


# --- phone ---------------------------------------------------------------

def test_phone_with_country_code_parses_without_region():
    assert normalize_phone("+1 415 555 0101").value == "+14155550101"


def test_phone_no_region_unparseable_abstains():
    result = normalize_phone("555-0188")
    assert result.abstained
    assert result.failed_method == "e164_no_region"
    assert result.value is None


def test_phone_region_inferred_from_context_enables_local_parse():
    # Same bare number, but with a known region -> parses (no fabrication: the
    # region is real context, not a guess).
    result = normalize_phone("(20) 7946 0958", NormContext(region="GB"))
    assert not result.abstained
    assert result.value.startswith("+44")


# --- date ----------------------------------------------------------------

def test_date_full_to_yyyy_mm():
    result = normalize_date("March 5, 2021")
    assert result.value == "2021-03"
    assert result.norm_quality == 1.0


def test_date_year_only_is_lenient():
    result = normalize_date("2019")
    assert result.value == "2019"
    assert result.norm_quality == 0.85
    assert result.note == "year_only"


def test_date_unparseable_abstains():
    assert normalize_date("not a date").abstained


def test_date_is_deterministic_no_wallclock():
    # A value with no day must not pull the day from the wall clock.
    assert normalize_date("2020-07").value == "2020-07"
    assert normalize_date("2020-07").value == "2020-07"


# --- country -------------------------------------------------------------

def test_country_name_to_alpha2():
    assert normalize_country("United Kingdom").value == "GB"


def test_country_alpha3_to_alpha2():
    assert normalize_country("USA").value == "US"


def test_country_unmappable_abstains():
    result = normalize_country("Atlantis")
    assert result.abstained
    assert result.failed_method == "iso3166"
