from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_streamlit_stub_runs():
    app = AppTest.from_file(APP).run()
    assert not app.exception
