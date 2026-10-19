from datetime import timedelta

from sqlalchemy import select, update

from app.db.base import utcnow
from app.models import PaperCache
from app.papers.base import PaperRecord
from app.services.citation_resolution import LookupStatus, PaperResolver, reference_title_match
from app.services.segmentation import ReferenceEntry
from tests.fakes import HF_DOI, FakePaperProvider


def _providers():
    return [FakePaperProvider.crossref_heart_failure(), FakePaperProvider.openalex_heart_failure()]


async def test_lookup_merges_providers_and_caches(db_session):
    providers = _providers()
    first = await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    assert first.status == LookupStatus.FOUND and not first.from_cache
    assert first.paper.abstract_source == "crossref"
    assert first.paper.open_access.oa_status == "hybrid"
    row = await db_session.scalar(select(PaperCache).where(PaperCache.doi == HF_DOI))
    assert row.providers == ["crossref", "openalex"]

    second = await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    assert second.from_cache and second.paper.title == first.paper.title
    assert [len(p.calls) for p in providers] == [1, 1]  # no repeat HTTP for the same DOI


async def test_memo_within_one_run(db_session):
    providers = _providers()
    resolver = PaperResolver(providers, cache_ttl_days=30)
    await resolver.lookup(db_session, HF_DOI)
    await resolver.lookup(db_session, HF_DOI, refresh=True)  # memo wins within a run
    assert len(providers[0].calls) == 1


async def test_refresh_bypasses_cache(db_session):
    providers = _providers()
    await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI, refresh=True)
    assert len(providers[0].calls) == 2


async def test_stale_cache_is_refetched(db_session):
    providers = _providers()
    await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    await db_session.execute(
        update(PaperCache)
        .where(PaperCache.doi == HF_DOI)
        .values(fetched_at=utcnow() - timedelta(days=31))
    )
    result = await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    assert not result.from_cache and len(providers[0].calls) == 2


async def test_not_found_is_negatively_cached(db_session):
    providers = _providers()
    doi = "10.9999/does-not-exist"
    assert (
        await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, doi)
    ).status == LookupStatus.NOT_FOUND
    again = await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, doi)
    assert again.status == LookupStatus.NOT_FOUND and again.from_cache
    assert len(providers[0].calls) == 1


async def test_provider_outage_is_unavailable_and_not_cached(db_session):
    providers = _providers()
    for p in providers:
        p.failures["*"] = "timeout"
    result = await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    assert result.status == LookupStatus.UNAVAILABLE
    assert set(result.errors) == {"crossref:timeout", "openalex:timeout"}
    assert await db_session.scalar(select(PaperCache).where(PaperCache.doi == HF_DOI)) is None


async def test_partial_outage_still_resolves(db_session):
    providers = _providers()
    providers[0].failures["*"] = "rate_limited"
    result = await PaperResolver(providers, cache_ttl_days=30).lookup(db_session, HF_DOI)
    assert result.status == LookupStatus.FOUND
    assert result.paper.abstract_source == "openalex"  # crossref unavailable
    row = await db_session.scalar(select(PaperCache).where(PaperCache.doi == HF_DOI))
    assert row.last_error == "crossref:rate_limited"


def test_reference_title_match():
    paper = PaperRecord(
        doi=HF_DOI, title="Remote patient monitoring in heart failure: a meta-analysis"
    )
    good = ReferenceEntry(
        "1", "Doe J. Remote patient monitoring in heart failure: a meta-analysis. 2025.", HF_DOI
    )
    bad = ReferenceEntry(
        "1", "Roe K. Statins and stroke prevention in older adults. Lancet 2019.", HF_DOI
    )
    assert reference_title_match(good, paper) == 1.0
    assert reference_title_match(bad, paper) == 0.0
    assert reference_title_match(ReferenceEntry("1", "doi:10.1/x", HF_DOI), paper) is None
    assert reference_title_match(None, paper) is None
