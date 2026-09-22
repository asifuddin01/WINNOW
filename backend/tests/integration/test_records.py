"""The records table: filters, the search syntax from guide 8.9, facets and paging."""

import uuid
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import MemoryMailer
from tests.integration.test_imports import run, upload
from tests.project_helpers import OWNER, REVIEWER, add_member, create_project, get, person, post


async def loaded(client: AsyncClient, db_app: FastAPI, name: str = "ovid_embase.ris") -> str:
    """A project with one file imported, ready to search."""
    project = await create_project(client)
    pid: str = project["id"]
    batch = await upload(client, pid, name)
    await post(client, f"/projects/{pid}/imports/{batch['id']}/confirm", {})
    await run(db_app, batch["id"])
    return pid


async def search(client: AsyncClient, pid: str, query: str, **extra: Any) -> list[str]:
    params = "&".join(f"{k}={v}" for k, v in extra.items())
    path = f"/projects/{pid}/records?q={query}" + (f"&{params}" if params else "")
    response = await get(client, path)
    assert response.status_code == 200, response.text
    return [record["title"] or "" for record in response.json()["items"]]


async def test_the_search_syntax(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        pid = await loaded(owner, db_app)

        assert len(await search(owner, pid, "")) == 2
        assert await search(owner, pid, "cohort") == [
            "Rotating night shifts and sleep quality among hospital nurses: "
            "a prospective cohort study"
        ]
        # A phrase, and a word ruled out.
        assert len(await search(owner, pid, "%22sleep+quality%22")) == 1
        assert len(await search(owner, pid, "shift+-conference")) == 1
        # Fielded terms.
        assert len(await search(owner, pid, "author%3Achowdhury")) == 1
        assert len(await search(owner, pid, "journal%3Anursing")) == 1
        assert len(await search(owner, pid, "year%3A2020")) == 1
        assert len(await search(owner, pid, "year%3A2019..2021")) == 2
        assert len(await search(owner, pid, "keyword%3Anurses")) == 1
        # An identifier on its own is a lookup.
        assert len(await search(owner, pid, "10.1111%2Fjan.13894")) == 1
        assert len(await search(owner, pid, "31234567")) == 1
        # Nonsense finds nothing rather than failing.
        assert await search(owner, pid, "kangaroo") == []


async def test_filters_sorting_and_paging(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        pid = await loaded(owner, db_app)
        page = (await get(owner, f"/projects/{pid}/records?limit=1")).json()
        assert len(page["items"]) == 1
        assert page["total"] == 2
        assert page["total_is_exact"] is True
        assert page["next_cursor"]

        second = (
            await get(owner, f"/projects/{pid}/records?limit=1&cursor={page['next_cursor']}")
        ).json()
        assert second["items"][0]["id"] != page["items"][0]["id"]
        assert second["next_cursor"] is None

        by_year = (await get(owner, f"/projects/{pid}/records?sort=year_asc")).json()["items"]
        assert [record["year"] for record in by_year] == [2019, 2020]
        by_title = (await get(owner, f"/projects/{pid}/records?sort=title")).json()["items"]
        assert by_title[0]["title"].startswith("Rotating")

        pending = await get(owner, f"/projects/{pid}/records?status=pending")
        assert pending.json()["total"] == 2
        included = await get(owner, f"/projects/{pid}/records?status=included")
        assert included.json()["total"] == 0
        batch_id = (await get(owner, f"/projects/{pid}/imports")).json()[0]["id"]
        assert (await get(owner, f"/projects/{pid}/records?batch={batch_id}")).json()["total"] == 2
        assert (await get(owner, f"/projects/{pid}/records?cursor=rubbish")).status_code == 400


async def test_facets_count_what_the_filters_offer(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        pid = await loaded(owner, db_app)
        facets = (await get(owner, f"/projects/{pid}/records/facets")).json()
        assert facets["total"] == 2
        assert facets["duplicates"] == 0
        assert {count["value"]: count["count"] for count in facets["title_abstract"]} == {
            "pending": 2
        }
        assert {count["value"] for count in facets["years"]} == {"2019", "2020"}
        assert facets["imports"][0]["count"] == 2


async def test_records_are_only_visible_to_members(db_app: FastAPI, mailer: MemoryMailer) -> None:
    async with (
        person(db_app, mailer, OWNER, ip="10.6.0.1") as owner,
        person(db_app, mailer, REVIEWER, ip="10.6.0.2") as reviewer,
        person(db_app, mailer, "stranger@example.org", ip="10.6.0.3") as stranger,
    ):
        pid = await loaded(owner, db_app)
        await add_member(owner, reviewer, pid, REVIEWER)
        # A reviewer reads them.
        assert (await get(reviewer, f"/projects/{pid}/records")).json()["total"] == 2
        assert (await get(reviewer, f"/projects/{pid}/records/facets")).status_code == 200
        # Nobody else knows the review exists.
        assert (await get(stranger, f"/projects/{pid}/records")).status_code == 404
        assert (await get(stranger, f"/projects/{pid}/records/{uuid.uuid4()}")).status_code == 404


async def test_a_record_from_another_review_is_not_found(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    async with person(db_app, mailer, OWNER) as owner:
        mine = await loaded(owner, db_app)
        other = await loaded(owner, db_app, "cochrane.ris")
        theirs = (await get(owner, f"/projects/{other}/records")).json()["items"][0]["id"]
        assert (await get(owner, f"/projects/{mine}/records/{theirs}")).status_code == 404


async def test_every_sort_order_pages_without_repeating_a_record(
    db_app: FastAPI, mailer: MemoryMailer
) -> None:
    """Each order ends with the record id, so a cursor always lands in one place."""
    async with person(db_app, mailer, OWNER) as owner:
        project = await create_project(owner)
        pid = project["id"]
        for name in ("ovid_embase.ris", "cochrane.ris", "wos.ris", "cinahl.ris"):
            batch = await upload(owner, pid, name)
            await post(owner, f"/projects/{pid}/imports/{batch['id']}/confirm", {})
            await run(db_app, batch["id"])
        total = (await get(owner, f"/projects/{pid}/records")).json()["total"]
        assert total == 5

        for sort in ("added", "oldest", "year", "year_asc", "title", "relevance"):
            seen: list[str] = []
            cursor: str | None = None
            for _ in range(10):  # more rounds than records, to catch a cursor that sticks
                path = f"/projects/{pid}/records?limit=2&sort={sort}"
                page = (await get(owner, f"{path}&cursor={cursor}" if cursor else path)).json()
                seen.extend(record["id"] for record in page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            assert len(seen) == len(set(seen)), f"{sort} repeated a record"
            assert len(seen) == total, f"{sort} missed records"
