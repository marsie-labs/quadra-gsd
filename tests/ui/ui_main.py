"""Main file for the NiceGUI ``user`` fixture. Tests inject services; this never sets any."""

from nicegui import ui

from app.ui import canvas_page

canvas_page.register()

ui.run(storage_secret="test-storage-secret-for-the-nicegui-user-fixture")
