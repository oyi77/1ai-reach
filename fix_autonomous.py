import sys
from pathlib import Path

target = Path("src/oneai_reach/application/agents/autonomous_service.py")
content = target.read_text()

if "from pathlib import Path" not in content:
    content = "from pathlib import Path\n" + content

target.write_text(content)
