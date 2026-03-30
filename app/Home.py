from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from neighbourhood_explorer.logging_config import configure_logging

configure_logging()

from app.components.page_views import render_home_page

render_home_page()
