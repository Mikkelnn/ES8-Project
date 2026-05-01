import json

INPUT_FILE = "map_gui\selected_roads_Aalborg.json"

with open(INPUT_FILE) as f:
    data = json.load(f)

roads = (data["Road_ID"]).keys()

print(roads)
