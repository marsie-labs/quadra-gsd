"""Single page-registration entry point, used by app/main.py and the test harness."""

from app.ui import canvas_page, home_page


def register_pages() -> None:
    home_page.register()
    canvas_page.register()
