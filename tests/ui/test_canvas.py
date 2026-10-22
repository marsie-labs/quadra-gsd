"""SESS-04: a second browser with no cookies and no login opens the same session."""

from app.deps import get_services
from app.models import QUADRANT_LABELS
from tests.ui.fakes import SEEDED_ID_A, SEEDED_NAME_A, install_fake_services

PATH = f"/s/{SEEDED_ID_A}"
KINDS = ("IS", "IS_NOT", "DOES", "DOES_NOT")
LABELS = ("IS", "IS NOT", "DOES", "DOES NOT")
LOGIN_PROMPTS = ("Log in", "Sign in", "Password")


async def _assert_canvas(browser) -> None:
    await browser.should_see(marker="project-name", content=SEEDED_NAME_A)
    for kind in KINDS:
        await browser.should_see(marker=f"quadrant-{kind}")
    for label in LABELS:
        await browser.should_see(label)
    for prompt in LOGIN_PROMPTS:
        await browser.should_not_see(prompt)


async def test_second_browser_opens_same_session_without_login(user, create_user):
    install_fake_services({SEEDED_ID_A: SEEDED_NAME_A})

    await user.open(PATH)
    await _assert_canvas(user)

    second = create_user()
    await second.open(PATH)
    await _assert_canvas(second)

    view = await get_services().sessions.get(SEEDED_ID_A)
    assert view is not None
    ordered = sorted(view.quadrants, key=lambda q: q.position)
    assert [q.position for q in ordered] == [1, 2, 3, 4]
    assert [q.kind for q in ordered] == list(KINDS)
    assert [QUADRANT_LABELS[q.kind] for q in ordered] == list(LABELS)
