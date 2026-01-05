# How to use (BETA)

## General Steps
- request an account from me
- log into https://fa-metrics.rancher.katzencluster.atlantishq.de/
- download and enable **FA_Metrics_Exporter** from the FAF modvault

## Windows
- download the latest released [fa-metrics-exporter-client.exe](https://github.com/FAUSheppy/fa-live-metrics-client/releases) it should automatically find the logs at the default location
- if logs are not at the default location execute the executeable with `--watch-dir C:/path/to/faf/log/` (the directory with files that look like `game_1234567.log`)

## Linux
- download or clone this repository
- install python via your package manager
- install dependencies with `python3 -m pip -r requirements.txt`
- run the script `python3 ingester.py`

## Notes
- not all alerts in the overview are already implemented
- the mod _can_ lag the UI, there is a hotkey you can map to unload it, should it ever happen
- if you want to start a game just open the **Live Game** page