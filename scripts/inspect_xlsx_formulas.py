"""xlsx 내 수식 XML 확인용 스크립트."""
import glob
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(sorted(glob.glob(str(ROOT / "data/output/SPC_*.xlsx")), reverse=True)[0])
print(path)
with zipfile.ZipFile(path) as z:
    for n in sorted(z.namelist()):
        if "/sheet" in n and n.endswith(".xml"):
            data = z.read(n).decode("utf-8")
            if "STDEV" in data or "@" in data:
                print("---", n)
                for m in re.finditer(r"<f[^>]*>[^<]*</f>", data):
                    if "STDEV" in m.group(0) or "@" in m.group(0):
                        print(" ", m.group(0))
