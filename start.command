#!/bin/zsh
cd "${0:A:h}"
if [[ -x ".venv/bin/python" ]]; then
  .venv/bin/python server.py
else
  python3 server.py
fi
