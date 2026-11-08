"""
Create_kg.py - Milestone 2: Formula 1 Knowledge Graph in Neo4j

What this script does (in simple words):
  1. Reads the Neo4j login details from config.txt (by KEY, not by line number).
  2. Reads 9 CSV files that sit in the SAME folder as this script.
  3. Builds the graph in this order:
        a) uniqueness constraints (so one ID = one node, and MERGE is fast)
        b) entity nodes : Driver, Constructor, Circuit, Season, Status
        c) Race nodes   : linked to Circuit and Season
        d) fact nodes   : Result, Qualifying, PitStop, linked to their parents
  4. Prints the final node / relationship counts so you can compare them
     with the expected 51,113 nodes and 163,510 relationships.

Safe to re-run: everything uses MERGE, so no duplicate nodes or relationships.
"""

import csv
import datetime
import os
import sys

from neo4j import GraphDatabase

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = "config.txt"
BATCH_SIZE = 2000                      # rows sent to Neo4j per transaction
MISSING = {"", "\\N"}                  # the literal \N and empty cells = missing

EXPECTED_NODES = 51113
EXPECTED_RELATIONSHIPS = 163510

# (label, identifier property) -> one uniqueness constraint each
CONSTRAINTS = [
    ("Driver", "driverId"),
    ("Constructor", "constructorId"),
    ("Circuit", "circuitId"),
    ("Season", "year"),
    ("Status", "statusId"),
    ("Race", "raceId"),
    ("Result", "resultId"),
    ("Qualifying", "qualifyId"),
    ("PitStop", "eventId"),
]


# --------------------------------------------------------------------------
# Reading the config file (read each value by its key)
# --------------------------------------------------------------------------
def read_config(path):
    config = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)       # split only on the first "="
            config[key.strip().upper()] = value.strip()
    for required in ("URI", "USERNAME", "PASSWORD"):
        if required not in config:
            sys.exit(f"config.txt is missing the key {required}")
    return config


# --------------------------------------------------------------------------
# Small helpers to read and convert CSV values
# --------------------------------------------------------------------------
def read_csv(filename):
    path = os.path.join(BASE_DIR, filename)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def clean(value):
    """Return the stripped text, or None if the value is missing (\\N or empty)."""
    if value is None:
        return None
    value = value.strip()
    return None if value in MISSING else value


def to_str(value):
    return clean(value)


def to_int(value):
    v = clean(value)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return int(float(v))            # handles values like "12.0"


def to_float(value):
    v = clean(value)
    return None if v is None else float(v)


def to_date(value):
    v = clean(value)
    return None if v is None else datetime.date.fromisoformat(v)


def get(row, *names):
    """Return the first column that exists (some datasets use different names)."""
    for name in names:
        if name in row:
            return row[name]
    return None


def props(**kwargs):
    """Keep only the properties that have a value, so missing ones are omitted."""
    return {k: v for k, v in kwargs.items() if v is not None}


# --------------------------------------------------------------------------
# Turning CSV rows into "rows for Neo4j"
# Each item has: id (the unique identifier), props (the other properties),
# plus the parent ids needed for relationships.
# --------------------------------------------------------------------------
def build_drivers(rows):
    return [{
        "id": to_int(r["driverId"]),
        "props": props(
            driverRef=to_str(r.get("driverRef")),
            number=to_int(r.get("number")),
            code=to_str(r.get("code")),
            forename=to_str(r.get("forename")),
            surname=to_str(r.get("surname")),
            dob=to_date(r.get("dob")),
            nationality=to_str(r.get("nationality")),
        ),
    } for r in rows]


def build_constructors(rows):
    return [{
        "id": to_int(r["constructorId"]),
        "props": props(
            constructorRef=to_str(r.get("constructorRef")),
            constructor_name=to_str(get(r, "constructor_name", "name")),
            constructor_nationality=to_str(
                get(r, "constructor_nationality", "nationality")),
        ),
    } for r in rows]


def build_circuits(rows):
    return [{
        "id": to_int(r["circuitId"]),
        "props": props(
            circuitRef=to_str(r.get("circuitRef")),
            circuit_name=to_str(get(r, "circuit_name", "name")),
            circuit_loc=to_str(get(r, "circuit_loc", "location")),
            circuit_country=to_str(get(r, "circuit_country", "country")),
            lat=to_float(r.get("lat")),
            lng=to_float(r.get("lng")),
            alt=to_int(r.get("alt")),
        ),
    } for r in rows]


def build_seasons(rows):
    return [{"id": to_int(r["year"]), "props": {}} for r in rows]


def build_statuses(rows):
    return [{
        "id": to_int(r["statusId"]),
        "props": props(status=to_str(r.get("status"))),
    } for r in rows]


def build_races(rows):
    return [{
        "id": to_int(r["raceId"]),
        "year": to_int(r["year"]),
        "circuitId": to_int(r["circuitId"]),
        "props": props(
            year=to_int(r["year"]),
            round=to_int(r.get("round")),
            name=to_str(r.get("name")),
            date=to_date(r.get("date")),
            time=to_str(r.get("time")),
        ),
    } for r in rows]


def build_results(rows):
    return [{
        "id": to_int(r["resultId"]),
        "raceId": to_int(r["raceId"]),
        "driverId": to_int(r["driverId"]),
        "constructorId": to_int(r["constructorId"]),
        "statusId": to_int(r["statusId"]),
        "props": props(
            number=to_int(r.get("number")),
            grid=to_int(r.get("grid")),
            position=to_int(r.get("position")),
            positionText=to_str(r.get("positionText")),
            positionOrder=to_int(r.get("positionOrder")),
            points=to_float(r.get("points")),
            laps=to_int(r.get("laps")),
            time=to_str(r.get("time")),
            milliseconds=to_int(r.get("milliseconds")),
            fastestLap=to_int(r.get("fastestLap")),
            rank=to_int(r.get("rank")),
            fastestLapTime=to_str(r.get("fastestLapTime")),
            fastestLapSpeed=to_float(r.get("fastestLapSpeed")),
        ),
    } for r in rows]


def build_qualifying(rows):
    return [{
        "id": to_int(r["qualifyId"]),
        "raceId": to_int(r["raceId"]),
        "driverId": to_int(r["driverId"]),
        "constructorId": to_int(r["constructorId"]),
        "props": props(
            number=to_int(r.get("number")),
            position=to_int(r.get("position")),
            q1=to_str(r.get("q1")),
            q2=to_str(r.get("q2")),      # empty q2 / q3 are simply omitted
            q3=to_str(r.get("q3")),
        ),
    } for r in rows]


def build_pit_stops(rows):
    out = []
    for r in rows:
        race_id = to_int(r["raceId"])
        driver_id = to_int(r["driverId"])
        stop = to_int(r["stop"])
        out.append({
            "id": f"{race_id}:{driver_id}:{stop}",      # eventId
            "raceId": race_id,
            "driverId": driver_id,
            "props": props(
                stop=stop,
                lap=to_int(r.get("lap")),
                time=to_str(r.get("time")),
                duration=to_str(r.get("duration")),
                milliseconds=to_int(r.get("milliseconds")),
            ),
        })
    return out


# --------------------------------------------------------------------------
# Talking to Neo4j
# --------------------------------------------------------------------------
def run_batches(session, query, rows):
    """Send the rows to Neo4j in batches, each batch in its own transaction."""
    write = getattr(session, "execute_write", None) or session.write_transaction
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        write(lambda tx, b=batch: tx.run(query, rows=b).consume())


def create_constraints(session):
    for label, key in CONSTRAINTS:
        name = f"{label.lower()}_{key.lower()}_unique"
        query = (f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                 f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
        try:
            session.run(query).consume()
        except Exception as error:                       # keep going, but tell me
            print(f"  warning: could not create constraint on {label}.{key}: {error}")


def load_nodes(session, label, id_key, rows):
    query = (f"UNWIND $rows AS row "
             f"MERGE (n:{label} {{{id_key}: row.id}}) "
             f"SET n += row.props")
    run_batches(session, query, rows)


RACE_QUERY = """
UNWIND $rows AS row
MERGE (r:Race {raceId: row.id})
SET r += row.props
WITH r, row
MATCH (c:Circuit {circuitId: row.circuitId})
MATCH (s:Season {year: row.year})
MERGE (r)-[:AT_CIRCUIT]->(c)
MERGE (r)-[:IN_SEASON]->(s)
"""

RESULT_QUERY = """
UNWIND $rows AS row
MERGE (f:Result {resultId: row.id})
SET f += row.props
WITH f, row
MATCH (race:Race {raceId: row.raceId})
MATCH (d:Driver {driverId: row.driverId})
MATCH (c:Constructor {constructorId: row.constructorId})
MATCH (s:Status {statusId: row.statusId})
MERGE (f)-[:FOR_RACE]->(race)
MERGE (f)-[:BY_DRIVER]->(d)
MERGE (f)-[:FOR_CONSTRUCTOR]->(c)
MERGE (f)-[:HAS_STATUS]->(s)
"""

QUALIFYING_QUERY = """
UNWIND $rows AS row
MERGE (f:Qualifying {qualifyId: row.id})
SET f += row.props
WITH f, row
MATCH (race:Race {raceId: row.raceId})
MATCH (d:Driver {driverId: row.driverId})
MATCH (c:Constructor {constructorId: row.constructorId})
MERGE (f)-[:FOR_RACE]->(race)
MERGE (f)-[:BY_DRIVER]->(d)
MERGE (f)-[:FOR_CONSTRUCTOR]->(c)
"""

PITSTOP_QUERY = """
UNWIND $rows AS row
MERGE (f:PitStop {eventId: row.id})
SET f += row.props
WITH f, row
MATCH (race:Race {raceId: row.raceId})
MATCH (d:Driver {driverId: row.driverId})
MERGE (f)-[:FOR_RACE]->(race)
MERGE (f)-[:BY_DRIVER]->(d)
"""


def print_totals(session):
    nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    print(f"\nNodes         : {nodes}  (expected {EXPECTED_NODES})")
    print(f"Relationships : {rels}  (expected {EXPECTED_RELATIONSHIPS})")
    if nodes == EXPECTED_NODES and rels == EXPECTED_RELATIONSHIPS:
        print("Counts match the expected totals.")
    else:
        print("Counts do NOT match. Check the CSV files and the messages above.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    config_path = os.path.join(BASE_DIR, CONFIG_FILE)
    if not os.path.exists(config_path):
        config_path = CONFIG_FILE          # fall back to the current folder
    config = read_config(config_path)
    database = config.get("DATABASE")      # optional; never hardcoded

    driver = GraphDatabase.driver(
        config["URI"], auth=(config["USERNAME"], config["PASSWORD"]))
    driver.verify_connectivity()
    driver = GraphDatabase.driver(
        config["URI"], auth=(config["USERNAME"], config["PASSWORD"]))
    driver.verify_connectivity()

    session = driver.session(database=database) if database else driver.session()
    with session:
        print("Creating constraints...")
        create_constraints(session)

        print("Loading entity nodes...")
        load_nodes(session, "Driver", "driverId",
                   build_drivers(read_csv("drivers.csv")))
        load_nodes(session, "Constructor", "constructorId",
                   build_constructors(read_csv("constructors.csv")))
        load_nodes(session, "Circuit", "circuitId",
                   build_circuits(read_csv("circuits.csv")))
        load_nodes(session, "Season", "year",
                   build_seasons(read_csv("seasons.csv")))
        load_nodes(session, "Status", "statusId",
                   build_statuses(read_csv("status.csv")))

        print("Loading Race nodes and their relationships...")
        run_batches(session, RACE_QUERY, build_races(read_csv("races.csv")))

        print("Loading Result nodes (26k rows, this takes a little while)...")
        run_batches(session, RESULT_QUERY, build_results(read_csv("results.csv")))

        print("Loading Qualifying nodes...")
        run_batches(session, QUALIFYING_QUERY,
                    build_qualifying(read_csv("qualifying.csv")))

        print("Loading PitStop nodes...")
        run_batches(session, PITSTOP_QUERY,
                    build_pit_stops(read_csv("pit_stops.csv")))

        print_totals(session)

    driver.close()


if __name__ == "__main__":
    main()
