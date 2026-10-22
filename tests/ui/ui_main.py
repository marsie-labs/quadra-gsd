"""Main file for the NiceGUI ``user`` fixture. Tests inject services; this never sets any."""

from nicegui import ui

from app.ui.pages import register_pages

register_pages()

ui.run(storage_secret="test-storage-secret-for-the-nicegui-user-fixture")
