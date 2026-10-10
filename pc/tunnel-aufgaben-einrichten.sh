#!/bin/bash
# Aufruf: ! ./pc/tunnel-aufgaben-einrichten.sh
cd "$(dirname "$0")" || exit 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$PWD/tunnel-aufgaben-einrichten.ps1")"
