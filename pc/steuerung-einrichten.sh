#!/bin/bash
# Aufruf: ! ./pc/steuerung-einrichten.sh
cd "$(dirname "$0")" || exit 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$PWD/steuerung-einrichten.ps1")"
