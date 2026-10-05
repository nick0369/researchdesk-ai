"""Portable entry point; works with embedded Python distributions too."""
import sys, runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
command=sys.argv.pop(1) if len(sys.argv)>1 else 'serve'
if command=='serve':
    import uvicorn
    uvicorn.run('researchdesk.app:app',host='127.0.0.1',port=8765)
elif command in ('report','data'):
    runpy.run_module('researchdesk.'+('report' if command=='report' else 'data_pipeline'),run_name='__main__')
elif command=='test':
    import pytest
    raise SystemExit(pytest.main([str(ROOT/'tests'),'-q',*sys.argv[1:]]))
else:
    raise SystemExit('Usage: python run.py [serve|report|data|test]')
