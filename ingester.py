import os
import json
import time
import sys
import re
import requests
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth
import argparse
import pathlib
import datetime
import tqdm
import sys
import platform
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, wait

# ------------ CONFIGURATION ------------ #

SUBMITTER = None
WATCH_DIR = None
TARGET_SERVER = "http://localhost:5000"
GAME_INFO_API = None
ARGS = None
MAX_TIME_NO_DATA_MINUTES = 3

MAX_FILE_AGE = 3600  # 1 hour in seconds
SEND_TIMEOUT = 15
HEADERS = {
    "Content-Type": "application/json",
    "Token":  "secret"
}


def get_faf_log_dir() -> Path:

    system = platform.system()

    if system == "Windows":
        # %APPDATA% is the correct source for Roaming
        appdata = Path(os.environ.get("APPDATA", ""))
        return appdata / "Forged Alliance Forever" / "logs"

    elif system == "Linux":
        home = Path.home()
        return home / ".faforever" / "logs"

    else:
        print(f"Unsupported operating system: {system}", file=sys.stderr)
        sys.exit(1)


def find_and_check_log_dir():

    global WATCH_DIR

    WATCH_DIR = get_faf_log_dir()

    if not WATCH_DIR.exists():
        print(f"WARNING: Log directory does not exist: {WATCH_DIR}", file=sys.stderr)
        sys.exit(1)

    if not WATCH_DIR.is_dir():
        print(f"WARNING: Path is not a directory: {WATCH_DIR}", file=sys.stderr)
        sys.exit(1)

    log_files = list(WATCH_DIR.glob("game_*.log"))

    if not log_files:
        print(f"WARNING: No game_*.log files found in {WATCH_DIR}", file=sys.stderr)
        sys.exit(1)

    # At this point everything is valid
    print(f"Found {len(log_files)} log files in {WATCH_DIR}")


def send_game_info(filepath, state):
    payload = {
        "file": filepath,
        "state": state,
        "submitter": SUBMITTER,
    }
    return requests.post(GAME_INFO_API, headers=HEADERS, json=payload)

def send_data(data):

    return requests.post(INSERT_API, headers=HEADERS, json=data)

def check_lobby_line(line):

    timestamp = int(datetime.datetime.now().timestamp())

    if line.startswith("info: LOBBY: starting with local uid of "):

        # EXAMPLE STRING #
        # info: LOBBY: starting with local uid of 1050 [Sheppy]

        # parse lobby start string #
        _, uid_and_name = line.split("info: LOBBY: starting with local uid of")
        uid, name = uid_and_name.split(" [")
        name_clean = name.replace("]", "").strip()

        return {
            "player_connect_info": {
                "playerId" : int(uid),
                "playerName": name_clean,
                "isSubmitter": True,
                "isHost": True, # we assume we are host unless we get a connect to host line next
                "firstSeen": timestamp
            }
        }

    if line.startswith("info: LOBBY: Connecting to host"):

        # EXAMPLE LINE #
        # info: LOBBY: Connecting to host "hurleyalex" [kubernetes.docker.internal:49744, uid=59896

        # parse host connect string #
        name_and_uid = line.split('info: LOBBY: Connecting to host "')[1]
        name, uid_dirty = name_and_uid.split('"')
        uid = uid_dirty.split(", uid=")[1].replace("]", "").strip()
        name_clean = name.replace("]", "").strip()
        print(json.dumps({
            "player_connect_info": {
                "playerId" : int(uid),
                "playerName": name_clean,
                "isSubmitter": False,
                "isHost": True,
                "firstSeen": timestamp
            },
            "connection_update" : {
                "playerId": 0,
                "connectionsList": [int(uid)],
                "connectionState": "connecting"
            }
        }, indent=2))

        return {
            "player_connect_info": {
                "playerId" : int(uid),
                "playerName": name_clean,
                "isSubmitter": False,
                "isHost": True,
                "firstSeen": timestamp
            },
            "connection_update" : {
                "playerId": 0,
                "connectionsList": [int(uid)],
                "connectionState": "connecting"
            }
        }

    if line.startswith("info: LOBBY: connection to"):


        # EXAMPLE LINE #
        #  info: LOBBY: connection to "hurleyalex" [kubernetes.docker.internal:49744, uid=59896] made, status=Connecting|Pending.

        pattern = re.compile(
            r'to\s+"(?P<name>[^"]+)".*?uid=(?P<uid>\d+).*?status=(?P<status>[^.\r\n]+)'
        )
        match = pattern.search(line)
        name = match.group('name')
        other_uid = match.group('uid')
        status = match.group('status')

        return {
            "player_connect_info": {
                "playerId" : int(other_uid),
                "playerName": name,
                "isSubmitter": False,
                "firstSeen": timestamp
            },
            "connection_update" : {
                "playerId": 0,
                "connectionsList": [int(other_uid)],
                "connectionState": status
            }
        }

    if line.startswith("info: ConnectToPeer"):

        # EXAMPLE LINE #
        # info: ConnectToPeer 127.0.0.1:58341 Tangamandapio   466357 <- legacy??
        # info: ConnectToPeer (name=AmonRa, uid=239673, address=127.0.0.1:62549, USE PROXY)

        elements = line.split("\t")
        if len(elements) < 2:
            # new style format #
            match = re.search(r"uid=(\d+)", line)
            other_uid = int(match.group(1)) if match else None
        else:
            other_uid = elements[-1]

        return {
            "connection_update" : {
                "playerId": 0,
                "connectionsList": [int(other_uid)],
                "connectionState": "connected"
            }
        }

    if "has established connections" in line:
        # "info: LOBBY: "j141" [kubernetes.docker.internal:55764, uid=322144] has established connections to: 1050, 59896, 239510, 353468, 466357"
        # update connection info
        left, connections = line.split("] has established connections to: ")
        match = re.search(r"uid=(\d+)", left)
        uid = int(match.group(1)) if match else None
        connections_list = [ int(x) for x in connections.split(", ")]

        return {
            "connection_update" : {
                "playerId": uid,
                "connectionsList": connections_list,
                "connectionState": "connected"
            }
        }

    ESTABLISHED_PEER_STRING = "debug: GpgNetSend   EstablishedPeer "
    if line.startswith(ESTABLISHED_PEER_STRING):

        # EXAMPLE LINE #
        # debug: GpgNetSend   EstablishedPeer 353468

        other_uid = line.split(ESTABLISHED_PEER_STRING)[1]

        # EXAMPLE LINE #
        # debug: GpgNetSend   EstablishedPeer 353468

        return {
            "connection_update" : {
                "playerId": 0,
                "connectionsList": [int(other_uid)],
                "connectionState": "connected"
            }
        }

    if line.startswith("info:         ") and " by " in line:

        # EXAMPLE LINE #
        # info:         "FA_Metrics_Exporter"           v01 (fa-metrics-exporter-01-sheppy)        by Sheppy

        mod = line.split("info:         ")[1]
        ws_collapse = re.compile(r'\s+')
        mod_clean = ws_collapse.sub(' ', mod)

        _, mod_name, right_string = mod_clean.split('"')
        pre_by, authors = right_string.split(" by ")
        version, mod_id = pre_by.strip().split(" ")
        
        return {
            "mod_info" : {
                "fullstring": mod_clean,
                "modVersion": version,
                "modId": mod_id.strip("()"),
                "modName": mod_name,
                "modAuthors": authors.strip()
            }
        }


def find_latest_game_log(directory: str, max_age: int):

    path = pathlib.Path(directory)

    files = [
        f for f in path.iterdir()
        if f.is_file() and f.name.startswith("game_")
    ]

    if not files:
        return None

    # check latest file max age #
    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    file_age = datetime.datetime.fromtimestamp(latest_file.stat().st_mtime)
    if not latest_file or file_age < datetime.datetime.now() - datetime.timedelta(hours=max_age):
        info_txt = f"({os.path.basename(latest_file)} ended at {file_age.strftime('%d.%m.%Y %H:%M')})"
        print(f"Latest file is too old as specified by --use-latest-max-age-hours {info_txt}")
        return

    return latest_file

def follow(filepath, ignore_conflict):

    with open(filepath, "r") as f:

        # track file #
        bulk = []
        eof_reached = False
        last_line_read = datetime.datetime.now()
        while True:

            # check for next line
            line = f.readline()

            # reached EOF, send everything that there #
            if not line:

                eof_reached = True

                # send data if present #
                if len(bulk) != 0:
                    send_data(bulk)
                    bulk = []

                #print(f"[{datetime.datetime.now().strftime("%H:%M:%S")}] Waiting for new line... [{os.path.basename(filepath)}]")
                time.sleep(0.1)

                if (datetime.datetime.now() - datetime.timedelta(minutes=MAX_TIME_NO_DATA_MINUTES) > last_line_read or
                        str(find_latest_game_log(WATCH_DIR, 1)) != filepath):
                    print("Aborting file follow despite no end line, no new lines in 5min. Game might have crashed.")
                    send_game_info(filepath, state="DONE")
                    return

                continue

            # output line #
            print("Line found:", line.strip("\n"))
            last_line_read = datetime.datetime.now()

            # check if is ending line #
            FILE_TERMINATORS = [
                "info: Run time:",
                "GpgNetSend	GameEnded",
                "info: CNetTCPBuf::Read(): recv() failed: WSAEINTR" # pretty common crash message
            ]
            if any(x in line  for x in FILE_TERMINATORS):
                print("Found end of file. Exiting follow & Sending done..")
                send_data(bulk)
                send_game_info(filepath, state="DONE")
                return

            # process lines & send to server #
            data, line_first_seen = process_line(line, filepath)
            if data:
                bulk.append(data)

            # send data if more than 300 lines #
            if len(bulk) > 1000 or (len(bulk) > 100 and eof_reached):
                send_data(bulk)
                if line_first_seen:
                    print("Time between line first seen and inserted:", datetime.datetime.now() - line_first_seen)
                bulk = []


def process_file(filepath: str):

    bulk_data = []

    print(f"Processing file: {filepath}")
    executor = ThreadPoolExecutor(max_workers=8)  # tune if needed
    futures = []
    with open(filepath, "r") as f:

        for line in f:
            data, line_first_seen = process_line(line, filepath)
            if data:
                bulk_data.append(data)

            # prevent very large requests #
            if len(bulk_data) > 150:
                futures.append(
                    executor.submit(
                        send_data,
                        bulk_data
                    )
                )
                bulk_data = []

    print("\nSubmitting final game information.. Waiting for server to ack it.")

    send_data(bulk_data)
    send_game_info(filepath, state="DONE")
    

    # progress bar for async requests
    TQDM_MSG = "Waiting for server to finish chunks"
    for future in tqdm.tqdm(as_completed(futures), total=len(futures), desc=TQDM_MSG):
        try:
            future.result()
        except Exception as e:
            print(f"Insert failed: {e}")

    executor.shutdown()


def process_line(line, filepath):

    global SUBMITTER

    # extract filename #
    source_file = os.path.basename(filepath)

    # linestart/line #
    linestart = "info: [FA_METRICS] JSON: "
    jsonline = None

    # check for self identifier first #
    # looks like this: 'info: LOBBY: starting with local uid of 1050 [Sheppy]'
    IDENT_STR = "info: LOBBY: starting with local uid of "
    if line.startswith(IDENT_STR):

        _, uid_and_name = line.split(IDENT_STR)
        uid, name_raw = uid_and_name.split(" ")
        name = name_raw.replace("[", "").replace("]", "").strip()
        SUBMITTER = name

        # record new game #
        response = send_game_info(filepath, state="NEW")
        if response.status_code == 409 and not ARGS.ignore_conflict:
            print(f"Game {os.path.basename(filepath)} already in db. Skipping..")
            raise ValueError("Game Already exists")



    # check if relevant metrics line #
    if line and line.startswith(linestart):

        jsonline = line.split(linestart)[1]

    else:

        # check for non-metrics data #
        line_first_seen = timestamp = int(datetime.datetime.now().timestamp())
        data = check_lobby_line(line)
        if data:
            data.update({ "file": source_file })
            return data, line_first_seen

        return None, None

    jsonline = jsonline.strip()
    if not jsonline:
        return None, None
    try:
        data = json.loads(jsonline)
        if type(data) not in [list, dict]:
            return None, None

        data.update({ "file": source_file })

        if "ratings" in data and not "time" in data:
            data.update({"time": 0})

        current_max_game_time =  data.get("time", -1)
        game_time_minutes, game_time_seconds = int(current_max_game_time / (60)), int(current_max_game_time  % 60)
        line_first_seen = datetime.datetime.now()
        print("Processed until Game Time: ", f"{game_time_minutes}:{game_time_seconds}\r", end="")
        return data, line_first_seen

    except json.JSONDecodeError:
        print(f"[WARN] invalid JSON: {filepath} {jsonline}")
        return None, None


def file_is_recent(filepath: str) -> bool:

    mtime = os.path.getmtime(filepath)
    return (time.time() - mtime) < MAX_FILE_AGE


if __name__ == "__main__":

    ap = argparse.ArgumentParser("FAF Metrics Ingester")
    ap.add_argument("--file")
    ap.add_argument("--watch-dir")
    ap.add_argument("--target-server", default="https://fa-metrics.rancher.katzencluster.atlantishq.de")
    ap.add_argument("--secret-token")
    ap.add_argument("--follow", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--use-latest", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--wait-for-new-file", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--ignore-conflict", action=argparse.BooleanOptionalAction, default=False, help="Write even if the game is aleady tracked in the DB.")
    ap.add_argument("--use-latest-max-age-hours", type=int, default=1)
    ap.add_argument("--simulate-live", action=argparse.BooleanOptionalAction, help="Simulate sending a existing file in real time")
    ap.add_argument("--load-sample-data", action=argparse.BooleanOptionalAction, default=False, help="Load Sample Data and ignore all other options")
    ap.add_argument("--submit-all", action=argparse.BooleanOptionalAction, default=False, help="Submit all file not on the server already")
    ap.add_argument("--submitter")
    args = ap.parse_args()

    ARGS = args

    # base args #
    if args.watch_dir:
        print(f"Watch-Dir set manually to {args.watchdir} we assume you know what you are doing..")
        WATCH_DIR = args.watch_dir
    else:
        find_and_check_log_dir()

    if args.target_server:
        TARGET_SERVER = args.target_server
    if args.secret_token:
        HEADERS["Token"] = args.secret_token

    if args.submitter:
        print("Warning --submitter is deprecated and will be ignored. Submitter is determined based on game-log.")

    # set API locations # 
    GAME_INFO_API = TARGET_SERVER + "/api/gameinfo"
    INSERT_API = TARGET_SERVER + "/api/insert"

    # sample data loading if requested #
    if args.load_sample_data:

        SAMPLE_NAME = "game_26119627.log"
        SAMPLE_DATA_HREF = f"https://media.atlantishq.de/faf-stuff/{SAMPLE_NAME}"
        print("--load-sample-data requested: Only loading example data, ignoring all other options!")

        # download example game log if not present #
        filepath = SAMPLE_NAME
        if not (os.path.isfile(SAMPLE_NAME) and os.stat(SAMPLE_NAME).st_size >= 59500000):
             # only import download conditionally #
            import download
            filepath = download.download_file(SAMPLE_DATA_HREF)

        # process file #
        start_time = datetime.datetime.now()
        process_file(filepath)
        end_time = datetime.datetime.now()

        print(f"-> Took {int((end_time - start_time).total_seconds())}s")
        print('''Sample Data loaded successfully:

            React Frontend: http://localhost:8081?gameid=26119627
            Flask Server: http://localhost:8080/games
            Database: localhost:5432 admin/adminpassword db: appdb
        ''')

        sys.exit(0)


    # check arguments #
    if args.file and args.use_latest:
        print("Can either specify --file or --use-latest", file=sys.stderr)
        sys.exit(1)
    elif args.wait_for_new_file and not (args.follow and args.use_latest):
        print("Auto targeting new file requires --follow and --use-latest as extra flags", file=sys.stderr)
        sys.exit(1)
    elif not (args.use_latest or args.file or args.submit_all):
        print("Must specify either --file or --use-latest", file=sys.stderr)
        sys.exit(1)
    elif args.simulate_live and not args.file:
        print("--simulate-live is only possible with --file", file=sys.stderr)
        sys.exit(1)
    elif args.simulate_live:
        print("--simulate-live is not implemented yet, sorry.", file=sys.stderr)
        sys.exit(1)
    elif args.submit_all and (args.use_latest or args.file):
        print("--submit-all not allowed with --use-latest or --file", file=sys.stderr)
        sys.exit(1)

    filename = args.file
    old_filename = ""

    if args.submit_all:

        path = pathlib.Path(WATCH_DIR)
        files = [
            f for f in path.iterdir()
            if f.is_file() and f.name.startswith("game_")
        ]

        latest = find_latest_game_log(WATCH_DIR, 2)
        for f in files:

            filepath = os.path.join(WATCH_DIR, f)
            # do not process latestet, potentially unfinished file #
            if filepath == latest:
                continue

        print(f"Submited all files in {WATCH_DIR}")
        sys.exit(0)

    while True:

        if args.use_latest:
            filename = find_latest_game_log(WATCH_DIR, args.use_latest_max_age_hours)
            if not filename or old_filename == filename:

                if args.wait_for_new_file:
                    # print("No suitable gamelog file found. Sleeping...")
                    time.sleep(2)
                    continue
                else:
                    sys.exit(0)

        print("Targeting File:",  filename)
        if not args.follow:
            print("Processing File (Single Run and Quit)")
            try:
                process_file(os.path.join(WATCH_DIR, filename))
            except ValueError as e:
                print(e)
        elif args.follow:
            print("Starting filetracker, Ctrl-C to abort..")
            try:
                follow(os.path.join(WATCH_DIR, filename), args.ignore_conflict)
            except ValueError as e:
                print(e)
        else:
            raise NotImplementedError()

        # abort condition #
        old_filename = filename
        if not args.wait_for_new_file:
            break
