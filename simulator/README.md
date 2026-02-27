## Imports
correct: `from simulator.x.y.z import module`
<br>
correct: `from node.x.y.z import module`
<br>
wrong: `from .x.y.z import module`
<br>
wrong: `from simulator.src.x.y.z import module`

## Run file
Always: `cd ES8-Project/simulator`
<br>
a) Main entry (GUI): `make run`
<br>
b) Profile: `make profile`
<br>
c) Custom module directly:
1. `make install`
2. `uv run python -m folder.sub_folder.file` ('folder' is relative to src)
