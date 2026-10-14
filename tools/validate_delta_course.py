"""Local structural checks and independent recovery model; does not run Fabric Spark."""
from pathlib import Path
import ast
import json
from decimal import Decimal

root = Path(__file__).resolve().parents[1]
folders = sorted(root.glob('DELTA *.Notebook'))
assert len(folders) == 15
ids = set()
cell_count = 0
for folder in folders:
    platform = json.loads((folder / '.platform').read_text(encoding='utf-8'))
    assert platform['metadata']['type'] == 'Notebook'
    assert platform['metadata']['displayName'] == folder.name.removesuffix('.Notebook')
    logical_id = platform['config']['logicalId']
    assert logical_id not in ids
    ids.add(logical_id)
    source = (folder / 'notebook-content.py').read_text(encoding='utf-8')
    assert source.startswith('# Fabric notebook source')
    assert '# MARKDOWN ********************' in source
    # Each contiguous META block must be valid JSON.
    for block in source.split('# METADATA ********************')[1:]:
        meta = '\n'.join(line[len('# META '):] for line in block.splitlines() if line.startswith('# META '))
        json.loads(meta)
    for block in source.split('# CELL ********************')[1:]:
        cell = block.split('# METADATA ********************')[0].strip()
        ast.parse(cell)
        cell_count += 1
    assert 'mlv_learn' not in source or folder.name.startswith('DELTA 14')
    assert 'default_lakehouse_workspace_id' not in source

# Independent model: extraction checkpoint must remain unchanged on partial failure.
source = {101:(Decimal('100'),False,1),102:(Decimal('200'),False,1),103:(Decimal('300'),False,1)}
silver, bronze = {}, set()
watermark = 0
gold = Decimal(0)
pending = None
def process(batch_id, fail=False):
    global watermark, gold, pending
    if pending is None:
        upper = max(v[2] for v in source.values())
        if upper <= watermark:
            return
        pending = (batch_id,upper,{k:v for k,v in source.items() if watermark < v[2] <= upper})
    batch_id, upper, rows = pending
    for key, value in rows.items():
        bronze.add((batch_id,key))
        if key not in silver or value[2] >= silver[key][2]:
            silver[key] = value
    if fail:
        return
    gold = sum((v[0] for v in silver.values() if not v[1]),Decimal(0))
    watermark = max(watermark,upper)
    pending = None

process('initial_001'); assert gold == 600
source[104] = (Decimal(50),False,2)
process('insert_001'); assert gold == 650
source[102] = (Decimal(250),False,3)
process('correction_001'); assert gold == 700
source[103] = (Decimal(300),True,4)
process('delete_001'); assert gold == 400
source[105] = (Decimal(75),False,5)
process('late_001'); assert gold == 475
before = len(bronze)
pending = ('late_001',5,{105:source[105]})
process('late_001'); assert gold == 475 and len(bronze) == before
source[106] = (Decimal(25),False,6)
process('recovery_001',fail=True)
assert watermark == 5 and gold == 475 and pending is not None
process('different_retry_request')
assert watermark == 6 and gold == 500 and len(bronze)==8 and len(silver)==6
assert sum(not v[1] for v in silver.values())==5
assert pending is None
print(f'PASS: {len(folders)} notebook items, {cell_count} Python cells, metadata and unique IDs')
print('PASS: independent sample arithmetic, replay and partial-failure recovery model')
print('Fabric Spark execution and UI integration remain workspace validation steps.')
