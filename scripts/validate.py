import json, pathlib, sys
root=pathlib.Path(__file__).resolve().parents[1]
d=json.loads((root/"data/daily.json").read_text(encoding="utf-8"))
assert "countries" in d and len(d["countries"])==31
assert "global_top" in d
print("OK:", d["version"], len(d["countries"]), "countries")
