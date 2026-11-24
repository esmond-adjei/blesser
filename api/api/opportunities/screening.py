"""Screen crawler pages with TypeSafe's Jev before paying for extraction; never blocks it."""

import logging
from dataclasses import dataclass, field

from typesafe_sdk import AsyncTypeSafeClient, Choice

from api.core.config import settings
from api.opportunities.page_content import Page
from api.opportunities.prompts import CATEGORY_BRIEFS

log = logging.getLogger(__name__)

NOT_ONE = "none"


@dataclass
class Screen:
    """`skip` is the triage reason when the page should not be extracted."""

    skip: str | None = None
    category: str | None = None
    answers: dict = field(default_factory=dict)


def questions(region: str, today: str) -> dict:
    return {
        "category": Choice(
            instructions=(
                "Which audience is this one listing for? Judge the page's main "
                "opportunity, not links to others."
            ),
            criteria={
                **CATEGORY_BRIEFS,
                NOT_ONE: (
                    "Not one specific opportunity: news, an index or list of many "
                    "opportunities, an organisation's general page, or no opportunity."
                ),
            },
        ),
        "region": Choice(
            instructions=f"Can people living in {region} apply?",
            criteria={
                "eligible": (
                    f"Open to people in {region}, to a wider area that includes it, "
                    "or no country restriction is stated."
                ),
                "excluded": (
                    f"Restricted to particular countries or regions that do not "
                    f"include {region}."
                ),
            },
        ),
        "open": Choice(
            instructions=f"Today is {today}. Can someone still apply?",
            criteria={
                "open": "A deadline today or later, rolling, or no deadline stated.",
                "closed": (
                    "Every deadline stated has passed, or the page says applications "
                    "are closed."
                ),
            },
        ),
    }


def state(page: Page) -> dict:
    return {
        "url": page.url,
        "title": page.title,
        "text": page.text[: settings.screen_max_chars],
    }


def decide(answers: dict, category: str, threshold: float) -> Screen:
    def sure(key: str, choice: str) -> bool:
        answer = answers.get(key)
        return (
            answer is not None
            and answer.choice == choice
            and (answer.confidence or 0) >= threshold
        )

    found = answers.get("category")
    picked = found.choice if found is not None else None
    # "Not one listing" is not trusted to skip: it threw away 7 of 62 good pages offline.
    if sure("open", "closed"):
        return Screen("deadline_passed", picked, answers)
    if sure("region", "excluded"):
        return Screen("region_excluded", picked, answers)
    if picked and picked not in (category, NOT_ONE) and sure("category", picked):
        return Screen("category_deferred", picked, answers)
    return Screen(None, picked, answers)


async def screen_page(page: Page, *, category: str, region: str, today: str) -> Screen:
    if not settings.screen_with_jev or not settings.typesafe_api_key:
        return Screen()
    try:
        async with AsyncTypeSafeClient(api_key=settings.typesafe_api_key) as client:
            response = await client.system_one(
                state=state(page),
                questions=questions(region, today),
                model=settings.typesafe_model,
                timeout=20,
            )
    except Exception as exc:  # noqa: BLE001 - the screen must never block extraction
        log.warning("Jev screen failed for %s: %s", page.url, exc)
        return Screen()
    return decide(response.answers, category, settings.screen_confidence)
