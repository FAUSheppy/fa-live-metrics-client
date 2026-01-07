# How to Use (BETA)

## General Steps
- Request an account from me with the following info:
    - FAF name: Sheppy (case-sensitive)
    - Optional: email address (for password resets)
- Log in to https://fa-metrics.rancher.katzencluster.atlantishq.de/
- Download and enable **UI mod tools** from the FAF-client mod vault
- Download and enable **FA_Metrics_Exporter** from the FAF-client mod vault

## Windows
- Download the latest released [fa-metrics-exporter-client.exe](https://github.com/FAUSheppy/fa-live-metrics-client/releases). It should automatically find the logs at the default location
- If the logs are not at the default location, execute the executable with `--watch-dir C:/path/to/faf/log/` (the directory containing files like `game_1234567.log`)

## Linux
- Download or clone this repository
- Install Python via your package manager
- Install dependencies with `python3 -m pip -r requirements.txt`
- Run the script with `python3 ingester.py`

## Notes
- Not all alerts in the overview are implemented yet
- The mod *can* lag the UI -> there is a hotkey you can map to unload it if this happens
- To start a game, simply open the **Live Game** page
