import httpx
import pytest
from pydantic import SecretStr

from app.papers.base import PaperProviderError, PaperRecord
from app.papers.crossref import CrossrefProvider, parse_crossref, parse_jats_abstract
from app.papers.openalex import OpenAlexProvider, parse_openalex, reconstruct_abstract
from app.seed.demo import PAPER
from app.services.citation_resolution import merge_records
from tests.fakes import HF_DOI, load_fixture


async def _no_sleep(_seconds: float) -> None:
    return None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_crossref_parsing_matches_verified_fixture():
    record = parse_crossref(HF_DOI, load_fixture("crossref_ejhf_3568.json")["message"])
    assert record.title == PAPER["title"]
    assert record.journal == "European Journal of Heart Failure"
    assert record.publication_year == 2025
    assert record.abstract == PAPER["abstract"]  # verbatim, incl. typographic spaces
    assert [s.title for s in record.abstract_sections] == [
        "Aims",
        "Methods and results",
        "Conclusion",
    ]
    assert record.authors[0]["family"] == "De Lathauwer"
    assert record.providers == ["crossref"]


def test_jats_without_sections_and_missing_abstract():
    assert parse_jats_abstract(None) == []
    sections = parse_jats_abstract(
        "<jats:title>Abstract</jats:title><jats:p>One &amp;lt; two.</jats:p>"
    )
    assert [(s.title, s.text) for s in sections] == [(None, "One < two.")]


def test_openalex_parsing_and_inverted_index():
    assert reconstruct_abstract({"world": [1], "hello": [0]}) == "hello world"
    assert reconstruct_abstract(None) is None
    record = parse_openalex(HF_DOI, load_fixture("openalex_ejhf_3568.json"))
    assert record.open_access.is_oa is True
    assert record.open_access.oa_status == "hybrid"
    assert record.abstract and "0.81" in record.abstract
    assert record.publication_year == 2025


def test_merge_prefers_crossref_bibliography_and_openalex_access():
    crossref = PaperRecord(doi=HF_DOI, title="CR title", journal=None, providers=["crossref"])
    openalex = PaperRecord.model_validate(
        {
            "doi": HF_DOI,
            "title": "OA title",
            "journal": "OA journal",
            "abstract": "OA abstract.",
            "abstract_source": "openalex",
            "abstract_sections": [{"text": "OA abstract."}],
            "open_access": {"is_oa": True, "oa_url": "https://oa.example/pdf"},
            "providers": ["openalex"],
        }
    )
    merged = merge_records(HF_DOI, [openalex, crossref])
    assert merged.title == "CR title"
    assert merged.journal == "OA journal"  # gap filled
    assert merged.abstract == "OA abstract." and merged.abstract_source == "openalex"
    assert merged.open_access.oa_url == "https://oa.example/pdf"
    assert merged.providers == ["crossref", "openalex"]


async def test_crossref_provider_request_and_not_found():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "missing" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json=load_fixture("crossref_ejhf_3568.json"))

    provider = CrossrefProvider(
        _client(handler), contact_email="ops@example.org", timeout=2, max_retries=0
    )
    record = await provider.get_by_doi(HF_DOI)
    assert record is not None and record.title == PAPER["title"]
    assert seen[0].url.path == "/works/10.1002/ejhf.3568"
    assert seen[0].url.params["mailto"] == "ops@example.org"
    assert await provider.get_by_doi("10.1000/missing") is None


async def test_crossref_omits_mailto_without_contact():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(404)

    await CrossrefProvider(
        _client(handler), contact_email=None, timeout=2, max_retries=0
    ).get_by_doi(HF_DOI)
    assert "mailto" not in seen[0].url.params


async def test_rate_limit_retried_with_retry_after():
    calls: list[int] = []
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1.5"})
        return httpx.Response(200, json=load_fixture("crossref_ejhf_3568.json"))

    provider = CrossrefProvider(
        _client(handler), contact_email=None, timeout=2, max_retries=2, sleep=record_sleep
    )
    assert await provider.get_by_doi(HF_DOI) is not None
    assert sleeps == [1.5]


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("t")), "timeout"),
        (lambda r: httpx.Response(503), "unavailable"),
        (lambda r: httpx.Response(429), "rate_limited"),
        (lambda r: httpx.Response(400), "bad_response"),
        (lambda r: httpx.Response(200, text="<html>"), "bad_response"),
    ],
)
async def test_provider_failures_raise_typed_errors(failure, kind):
    provider = OpenAlexProvider(
        _client(failure),
        contact_email=None,
        api_key=None,
        timeout=2,
        max_retries=1,
        sleep=_no_sleep,
    )
    with pytest.raises(PaperProviderError) as exc:
        await provider.get_by_doi(HF_DOI)
    assert (exc.value.provider, exc.value.kind) == ("openalex", kind)


async def test_openalex_request_shape_and_optional_key():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=load_fixture("openalex_ejhf_3568.json"))

    provider = OpenAlexProvider(
        _client(handler), contact_email=None, api_key=SecretStr("oa-key"), timeout=2, max_retries=0
    )
    record = await provider.get_by_doi(HF_DOI)
    assert record is not None and record.providers == ["openalex"]
    assert seen[0].url.path == "/works/https://doi.org/10.1002/ejhf.3568"
    assert seen[0].url.params["api_key"] == "oa-key"
