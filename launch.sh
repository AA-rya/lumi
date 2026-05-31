#!/bin/bash
echo "Starting Lumi at http://localhost:8080"
open http://localhost:8080
python3 -m http.server 8080
