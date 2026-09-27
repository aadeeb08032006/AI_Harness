import sys
from backend.app.tui import HarnessTUI

app = HarnessTUI(demo_mode=False, repo_url="", branch="", task="")
app.run()
