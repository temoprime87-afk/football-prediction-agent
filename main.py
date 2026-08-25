import json
import math
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ============================================================
# FPL AUTONOMOUS ANALYST
# ============================================================
#
# No API KEY required.
#
# Main outputs:
#   - Best 15-player squad under £100m
#   - Starting XI
#   - Bench
#   - Captain
#   - Vice-Captain
#   - Fixture analysis
#   - Match predictions
#   - Correct-score probabilities
#   - Likely goal scorers
#
# Data source:
#   Official Fantasy Premier League public API
#
# ============================================================


BASE_URL = "https://fantasy.premierleague.com/api"

TEAM_ID = 9623737

BUDGET = 100.0

SQUAD_SIZE = 15

MAX_PER_CLUB = 3

TOP_CANDIDATES_PER_POSITION = 80

UPCOMING_FIXTURES_TO_ANALYSE = 5

REQUEST_DELAY = 0.15

USER_AGENT = (
    "Mozilla/5.0 "
    "(Linux; Android 14) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Mobile Safari/537.36"
)


# ============================================================
# POSITION DATA
# ============================================================

POSITION_NAMES = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}


SQUAD_REQUIREMENTS = {
    "GK": 2,
    "DEF": 5,
    "MID": 5,
    "FWD": 3,
}


STARTING_FORMATIONS = [
    (3, 4, 3),
    (3, 5, 2),
    (4, 3, 3),
    (4, 4, 2),
    (4, 5, 1),
    (5, 3, 2),
    (5, 4, 1),
]


# ============================================================
# HTTP
# ============================================================

def get_json(url, retries=4):

    last_error = None

    for attempt in range(retries):

        try:

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Referer": (
                        "https://fantasy.premierleague.com/"
                    ),
                },
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                raw = response.read().decode(
                    "utf-8"
                )

                time.sleep(
                    REQUEST_DELAY
                )

                return json.loads(raw)

        except urllib.error.HTTPError as error:

            last_error = (
                f"HTTP {error.code}: "
                f"{error.reason}"
            )

            if error.code in (
                429,
                500,
                502,
                503,
                504,
            ):

                time.sleep(
                    2 + attempt * 2
                )

                continue

            break

        except urllib.error.URLError as error:

            last_error = (
                f"Network error: "
                f"{error.reason}"
            )

            time.sleep(
                2 + attempt * 2
            )

        except Exception as error:

            last_error = str(error)

            time.sleep(
                2 + attempt * 2
            )

    raise RuntimeError(
        f"{last_error} | URL: {url}"
    )


# ============================================================
# SAFE CONVERSIONS
# ============================================================

def number(value, default=0.0):

    try:

        if value is None:
            return default

        return float(value)

    except:

        return default


def integer(value, default=0):

    try:

        if value is None:
            return default

        return int(value)

    except:

        return default


def clamp(value, minimum, maximum):

    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def round2(value):

    return round(
        number(value),
        2,
    )


def money_from_fpl_cost(value):

    return round(
        number(value) / 10,
        1,
    )


# ============================================================
# POISSON
# ============================================================

def poisson_probability(
    goals,
    expected_goals,
):

    expected_goals = max(
        expected_goals,
        0.01,
    )

    return (
        math.exp(-expected_goals)
        *
        (
            expected_goals ** goals
        )
        /
        math.factorial(goals)
    )


# ============================================================
# LOAD FPL DATABASE
# ============================================================

def load_fpl_database():

    print("")
    print("=" * 60)
    print("LOADING OFFICIAL FPL DATABASE")
    print("=" * 60)

    bootstrap = get_json(
        f"{BASE_URL}/bootstrap-static/"
    )

    fixtures = get_json(
        f"{BASE_URL}/fixtures/"
    )

    players = bootstrap.get(
        "elements",
        [],
    )

    events = bootstrap.get(
        "events",
        [],
    )

    teams = bootstrap.get(
        "teams",
        [],
    )

    print(
        "Players:",
        len(players),
    )

    print(
        "Teams:",
        len(teams),
    )

    print(
        "Fixtures:",
        len(fixtures),
    )

    print(
        "Gameweeks:",
        len(events),
    )

    return {
        "bootstrap": bootstrap,
        "players": players,
        "events": events,
        "teams": teams,
        "fixtures": fixtures,
    }


# ============================================================
# GAMEWEEK
# ============================================================

def get_gameweek_info(events):

    current = None
    next_event = None

    for event in events:

        if event.get("is_current"):

            current = integer(
                event.get("id")
            )

        if event.get("is_next"):

            next_event = integer(
                event.get("id")
            )


    if current is None:

        for event in events:

            if event.get("finished"):

                current = integer(
                    event.get("id")
                )


    if current is None:

        current = 0


    if next_event is None:

        next_event = current + 1


    return {
        "current": current,
        "next": next_event,
    }


# ============================================================
# TEAM LOOKUP
# ============================================================

def build_team_lookup(teams):

    lookup = {}

    for team in teams:

        team_id = integer(
            team.get("id")
        )

        lookup[team_id] = team

    return lookup


# ============================================================
# FIXTURE MAP
# ============================================================

def build_fixture_map(
    fixtures
):

    fixture_map = {}

    for fixture in fixtures:

        event = fixture.get(
            "event"
        )

        if event is None:
            continue

        event = integer(event)

        home_team = integer(
            fixture.get("team_h")
        )

        away_team = integer(
            fixture.get("team_a")
        )

        if not home_team or not away_team:
            continue


        home_difficulty = number(
            fixture.get(
                "team_h_difficulty",
                3,
            ),
            3,
        )

        away_difficulty = number(
            fixture.get(
                "team_a_difficulty",
                3,
            ),
            3,
        )


        fixture_map.setdefault(
            home_team,
            [],
        ).append({

            "event": event,

            "opponent": away_team,

            "home": True,

            "difficulty":
                home_difficulty,

            "finished":
                bool(
                    fixture.get(
                        "finished",
                        False,
                    )
                ),

            "kickoff":
                fixture.get(
                    "kickoff_time"
                ),

            "fixture_id":
                fixture.get("id"),

        })


        fixture_map.setdefault(
            away_team,
            [],
        ).append({

            "event": event,

            "opponent": home_team,

            "home": False,

            "difficulty":
                away_difficulty,

            "finished":
                bool(
                    fixture.get(
                        "finished",
                        False,
                    )
                ),

            "kickoff":
                fixture.get(
                    "kickoff_time"
                ),

            "fixture_id":
                fixture.get("id"),

        })


    return fixture_map


# ============================================================
# UPCOMING FIXTURES
# ============================================================

def get_upcoming_fixtures(
    team_id,
    fixture_map,
    current_gameweek,
    limit=5,
):

    fixtures = []

    for fixture in fixture_map.get(
        team_id,
        [],
    ):

        if fixture["finished"]:
            continue

        if fixture["event"] <= current_gameweek:
            continue

        fixtures.append(
            fixture
        )


    fixtures.sort(
        key=lambda item:
        item["event"]
    )


    return fixtures[:limit]


# ============================================================
# FIXTURE SCORE
# ============================================================

def calculate_fixture_score(
    upcoming,
):

    if not upcoming:

        return 2.5


    values = []

    for fixture in upcoming:

        difficulty = clamp(
            number(
                fixture.get(
                    "difficulty",
                    3,
                ),
                3,
            ),
            1,
            5,
        )

        # FPL difficulty:
        # 1 = easiest
        # 5 = hardest

        score = (
            6 - difficulty
        )

        values.append(
            score
        )


    average = (
        sum(values)
        /
        len(values)
    )


    return clamp(
        average,
        0,
        5,
    )


# ============================================================
# PLAYER ANALYSIS
# ============================================================

def analyse_player(
    player,
    team_lookup,
    fixture_map,
    current_gameweek,
):

    player_id = integer(
        player.get("id")
    )

    team_id = integer(
        player.get("team")
    )

    position_id = integer(
        player.get(
            "element_type"
        )
    )

    team = team_lookup.get(
        team_id,
        {},
    )


    name = player.get(
        "web_name",
        "Unknown",
    )

    first_name = player.get(
        "first_name",
        "",
    )

    second_name = player.get(
        "second_name",
        "",
    )


    full_name = (
        f"{first_name} "
        f"{second_name}"
    ).strip()


    position = POSITION_NAMES.get(
        position_id,
        "?",
    )

    club = team.get(
        "short_name",
        "UNK",
    )


    price = money_from_fpl_cost(
        player.get("now_cost")
    )


    total_points = number(
        player.get(
            "total_points"
        )
    )

    form = number(
        player.get("form")
    )

    points_per_game = number(
        player.get(
            "points_per_game"
        )
    )

    minutes = number(
        player.get("minutes")
    )

    starts = number(
        player.get("starts")
    )

    goals = number(
        player.get(
            "goals_scored"
        )
    )

    assists = number(
        player.get(
            "assists"
        )
    )

    clean_sheets = number(
        player.get(
            "clean_sheets"
        )
    )

    bonus = number(
        player.get(
            "bonus"
        )
    )

    ict_index = number(
        player.get(
            "ict_index"
        )
    )

    influence = number(
        player.get(
            "influence"
        )
    )

    creativity = number(
        player.get(
            "creativity"
        )
    )

    threat = number(
        player.get(
            "threat"
        )
    )

    expected_goals = number(
        player.get(
            "expected_goals"
        )
    )

    expected_assists = number(
        player.get(
            "expected_assists"
        )
    )

    expected_goal_involvement = (
        expected_goals
        +
        expected_assists
    )


    chance_current = player.get(
        "chance_of_playing_this_round"
    )

    chance_next = player.get(
        "chance_of_playing_next_round"
    )


    if chance_current is None:
        chance_current = 100

    else:
        chance_current = number(
            chance_current
        )


    if chance_next is None:
        chance_next = 100

    else:
        chance_next = number(
            chance_next
        )


    status = player.get(
        "status"
    )


    # --------------------------------------------------------
    # MINUTES / STARTING PROBABILITY
    # --------------------------------------------------------

    minutes_per_appearance = (
        minutes
        /
        max(
            starts,
            1,
        )
    )


    minutes_score = clamp(
        minutes / 1000,
        0,
        1,
    )


    start_score = clamp(
        starts / 20,
        0,
        1,
    )


    availability_score = (
        chance_current / 100
    )


    # --------------------------------------------------------
    # FORM
    # --------------------------------------------------------

    form_score = clamp(
        form / 10,
        0,
        2,
    )


    ppg_score = clamp(
        points_per_game / 8,
        0,
        1.5,
    )


    # --------------------------------------------------------
    # ATTACK
    # --------------------------------------------------------

    xgi_score = clamp(
        expected_goal_involvement / 10,
        0,
        2,
    )


    goal_score = clamp(
        goals / 10,
        0,
        1.5,
    )


    assist_score = clamp(
        assists / 10,
        0,
        1,
    )


    # --------------------------------------------------------
    # ICT
    # --------------------------------------------------------

    ict_score = clamp(
        ict_index / 200,
        0,
        1,
    )


    influence_score = clamp(
        influence / 500,
        0,
        1,
    )


    creativity_score = clamp(
        creativity / 500,
        0,
        1,
    )


    threat_score = clamp(
        threat / 500,
        0,
        1,
    )


    # --------------------------------------------------------
    # UPCOMING FIXTURES
    # --------------------------------------------------------

    upcoming = get_upcoming_fixtures(
        team_id,
        fixture_map,
        current_gameweek,
        UPCOMING_FIXTURES_TO_ANALYSE,
    )


    fixture_score = calculate_fixture_score(
        upcoming
    )


    # --------------------------------------------------------
    # POSITION WEIGHTS
    # --------------------------------------------------------

    if position == "FWD":

        attack_weight = 1.45
        clean_sheet_weight = 0.10

    elif position == "MID":

        attack_weight = 1.35
        clean_sheet_weight = 0.15

    elif position == "DEF":

        attack_weight = 0.60
        clean_sheet_weight = 0.75

    else:

        attack_weight = 0.25
        clean_sheet_weight = 0.90


    clean_sheet_score = clamp(
        clean_sheets / 10,
        0,
        1,
    )


    # --------------------------------------------------------
    # CORE FPL SCORE
    # --------------------------------------------------------

    score = (

        form_score * 2.00

        +

        ppg_score * 1.30

        +

        minutes_score * 1.00

        +

        start_score * 0.80

        +

        fixture_score * 0.95

        +

        xgi_score * attack_weight

        +

        goal_score * 0.40

        +

        assist_score * 0.30

        +

        ict_score * 0.45

        +

        influence_score * 0.15

        +

        creativity_score * 0.15

        +

        threat_score * 0.15

        +

        clean_sheet_score
        * clean_sheet_weight

        +

        bonus * 0.025

        +

        availability_score * 1.20

    )


    # --------------------------------------------------------
    # AVAILABILITY PENALTY
    # --------------------------------------------------------

    if chance_current < 25:

        score *= 0.20

    elif chance_current < 50:

        score *= 0.45

    elif chance_current < 75:

        score *= 0.75


    if minutes_per_appearance < 45:

        score *= 0.80


    # --------------------------------------------------------
    # VALUE
    # --------------------------------------------------------

    if price > 0:

        value_score = (
            score / price
        )

    else:

        value_score = 0


    # --------------------------------------------------------
    # EXPECTED GOALS PER 90
    #
    # Bootstrap expected_goals is season-to-date.
    # We normalise it by minutes when possible.
    # --------------------------------------------------------

    if minutes > 0:

        xg_per_90 = (
            expected_goals
            /
            minutes
            *
            90
        )

        xa_per_90 = (
            expected_assists
            /
            minutes
            *
            90
        )

    else:

        xg_per_90 = 0
        xa_per_90 = 0


    # --------------------------------------------------------
    # LIKELY STARTER
    # --------------------------------------------------------

    starter_probability = clamp(
        (
            0.50 * availability_score
            +
            0.25 * start_score
            +
            0.25 * minutes_score
        ),
        0,
        1,
    )


    return {

        "id":
            player_id,

        "name":
            name,

        "full_name":
            full_name,

        "position":
            position,

        "position_id":
            position_id,

        "team_id":
            team_id,

        "team":
            club,

        "price":
            price,

        "total_points":
            int(total_points),

        "form":
            round2(form),

        "points_per_game":
            round2(points_per_game),

        "minutes":
            int(minutes),

        "starts":
            int(starts),

        "minutes_per_start":
            round2(minutes_per_appearance),

        "goals":
            int(goals),

        "assists":
            int(assists),

        "clean_sheets":
            int(clean_sheets),

        "bonus":
            int(bonus),

        "expected_goals":
            round2(expected_goals),

        "expected_assists":
            round2(expected_assists),

        "expected_goal_involvement":
            round2(
                expected_goal_involvement
            ),

        "xg_per_90":
            round2(xg_per_90),

        "xa_per_90":
            round2(xa_per_90),

        "ict_index":
            round2(ict_index),

        "influence":
            round2(influence),

        "creativity":
            round2(creativity),

        "threat":
            round2(threat),

        "chance_this_round":
            chance_current,

        "chance_next_round":
            chance_next,

        "status":
            status,

        "fixture_score":
            round2(
                fixture_score
            ),

        "starter_probability":
            round(
                starter_probability * 100,
                1,
            ),

        "agent_score":
            round(
                score,
                3,
            ),

        "value_score":
            round(
                value_score,
                3,
            ),

        "upcoming_fixtures":
            upcoming,

    }


# ============================================================
# PLAYER POOL
# ============================================================

def build_player_pool(
    players,
    team_lookup,
    fixture_map,
    current_gameweek,
):

    analysed = []

    for player in players:

        try:

            result = analyse_player(
                player,
                team_lookup,
                fixture_map,
                current_gameweek,
            )

            analysed.append(
                result
            )

        except Exception as error:

            print(
                "Player analysis skipped:",
                error,
            )


    return analysed


# ============================================================
# POSITION FILTER
# ============================================================

def by_position(
    players,
    position,
):

    return [

        player

        for player in players

        if player["position"] == position

    ]


# ============================================================
# REMOVE IMPOSSIBLE PLAYERS
# ============================================================

def usable_players(
    players
):

    result = []

    for player in players:

        if player["price"] <= 0:
            continue

        if player[
            "chance_this_round"
        ] < 25:

            continue

        result.append(
            player
        )


    return result


# ============================================================
# SQUAD COST
# ============================================================

def squad_cost(
    squad
):

    return round(
        sum(
            player["price"]
            for player in squad
        ),
        1,
    )


# ============================================================
# CLUB COUNT
# ============================================================

def club_count(
    squad,
    team_id,
):

    return sum(
        1
        for player in squad
        if player["team_id"] == team_id
    )


# ============================================================
# SQUAD VALIDATION
# ============================================================

def valid_squad(
    squad
):

    if len(squad) != SQUAD_SIZE:
        return False


    counts = {
        "GK": 0,
        "DEF": 0,
        "MID": 0,
        "FWD": 0,
    }


    for player in squad:

        position = player[
            "position"
        ]

        counts[position] += 1


    for position, required in (
        SQUAD_REQUIREMENTS.items()
    ):

        if counts[position] != required:

            return False


    clubs = {}

    for player in squad:

        team_id = player[
            "team_id"
        ]

        clubs[team_id] = (
            clubs.get(
                team_id,
                0,
            )
            + 1
        )


    if any(
        count > MAX_PER_CLUB
        for count in clubs.values()
    ):

        return False


    if squad_cost(squad) > BUDGET:

        return False


    return True


# ============================================================
# INITIAL SQUAD
# ============================================================

def create_initial_squad(
    players
):

    squad = []


    for position, required in (
        SQUAD_REQUIREMENTS.items()
    ):

        candidates = by_position(
            players,
            position,
        )


        candidates.sort(
            key=lambda player:
            (
                player["price"],
                -player["agent_score"],
            )
        )


        for player in candidates:

            if len(
                [
                    p
                    for p in squad
                    if p["position"] == position
                ]
            ) >= required:

                break


            if club_count(
                squad,
                player["team_id"],
            ) >= MAX_PER_CLUB:

                continue


            squad.append(
                player
            )


    if not valid_squad(
        squad
    ):

        return None


    return squad


# ============================================================
# SQUAD SCORE
# ============================================================

def squad_score(
    squad
):

    return sum(
        player["agent_score"]
        for player in squad
    )


# ============================================================
# UPGRADE SQUAD
# ============================================================

def improve_squad(
    squad,
    players,
):

    if not squad:

        return None


    squad = list(
        squad
    )


    position_groups = {

        position:
        by_position(
            players,
            position,
        )

        for position
        in SQUAD_REQUIREMENTS

    }


    improved = True

    passes = 0


    while improved and passes < 50:

        improved = False

        passes += 1


        current_score = squad_score(
            squad
        )


        for index, old_player in enumerate(
            list(squad)
        ):

            candidates = position_groups[
                old_player["position"]
            ]


            candidates = sorted(
                candidates,
                key=lambda player:
                player["agent_score"],
                reverse=True,
            )


            for new_player in candidates:

                if new_player["id"] in {
                    p["id"]
                    for p in squad
                }:

                    continue


                if (
                    new_player["agent_score"]
                    <=
                    old_player["agent_score"]
                ):

                    continue


                trial = list(
                    squad
                )

                trial[index] = (
                    new_player
                )


                if not valid_squad(
                    trial
                ):

                    continue


                new_score = squad_score(
                    trial
                )


                if new_score > current_score:

                    squad = trial

                    improved = True

                    break


            if improved:

                break


    return squad


# ============================================================
# FIND BEST SQUAD
# ============================================================

def build_best_squad(
    players
):

    candidates = usable_players(
        players
    )


    # Keep strongest candidates per position
    reduced = []


    for position in SQUAD_REQUIREMENTS:

        position_players = by_position(
            candidates,
            position,
        )


        position_players.sort(
            key=lambda player:
            player["agent_score"],
            reverse=True,
        )


        reduced.extend(
            position_players[
                :TOP_CANDIDATES_PER_POSITION
            ]
        )


    initial = create_initial_squad(
        reduced
    )


    if not initial:

        print(
            "Could not create initial squad."
        )

        return None


    best = improve_squad(
        initial,
        reduced,
    )


    return best


# ============================================================
# FORMATION VALIDATION
# ============================================================

def can_use_formation(
    squad,
    formation
):

    defenders_needed = formation[0]
    midfielders_needed = formation[1]
    forwards_needed = formation[2]


    if len(
        by_position(
            squad,
            "GK",
        )
    ) < 1:

        return False


    if len(
        by_position(
            squad,
            "DEF",
        )
    ) < defenders_needed:

        return False


    if len(
        by_position(
            squad,
            "MID",
        )
    ) < midfielders_needed:

        return False


    if len(
        by_position(
            squad,
            "FWD",
        )
    ) < forwards_needed:

        return False


    return True


# ============================================================
# STARTING XI
# ============================================================

def build_starting_xi(
    squad
):

    best_lineup = None


    for formation in STARTING_FORMATIONS:

        if not can_use_formation(
            squad,
            formation,
        ):

            continue


        defenders_needed = formation[0]
        midfielders_needed = formation[1]
        forwards_needed = formation[2]


        gks = sorted(
            by_position(
                squad,
                "GK",
            ),
            key=lambda p:
            p["agent_score"],
            reverse=True,
        )


        defs = sorted(
            by_position(
                squad,
                "DEF",
            ),
            key=lambda p:
            p["agent_score"],
            reverse=True,
        )


        mids = sorted(
            by_position(
                squad,
                "MID",
            ),
            key=lambda p:
            p["agent_score"],
            reverse=True,
        )


        fwds = sorted(
            by_position(
                squad,
                "FWD",
            ),
            key=lambda p:
            p["agent_score"],
            reverse=True,
        )


        lineup = []

        lineup.append(
            gks[0]
        )

        lineup.extend(
            defs[
                :defenders_needed
            ]
        )

        lineup.extend(
            mids[
                :midfielders_needed
            ]
        )

        lineup.extend(
            fwds[
                :forwards_needed
            ]
        )


        if len(lineup) != 11:

            continue


        score = sum(
            player["agent_score"]
            for player in lineup
        )


        # Extra reward for high starter probability
        score += sum(
            player[
                "starter_probability"
            ] / 100
            for player in lineup
        )


        candidate = {

            "formation":
                formation,

            "players":
                lineup,

            "score":
                round(
                    score,
                    3,
                ),

        }


        if (
            best_lineup is None
            or
            candidate["score"]
            >
            best_lineup["score"]
        ):

            best_lineup = candidate


    return best_lineup


# ============================================================
# BENCH
# ============================================================

def build_bench(
    squad,
    starting_xi,
):

    starting_ids = {
        player["id"]
        for player
        in starting_xi["players"]
    }


    bench = [

        player

        for player in squad

        if player["id"]
        not in starting_ids

    ]


    # Best first substitute,
    # but preserve goalkeeper as last bench slot.
    outfield = [
        p
        for p in bench
        if p["position"] != "GK"
    ]

    goalkeeper = [
        p
        for p in bench
        if p["position"] == "GK"
    ]


    outfield.sort(
        key=lambda p:
        p["agent_score"],
        reverse=True,
    )


    goalkeeper.sort(
        key=lambda p:
        p["agent_score"],
        reverse=True,
    )


    ordered = outfield

    if goalkeeper:

        ordered.extend(
            goalkeeper
        )


    return ordered


# ============================================================
# CAPTAIN SCORE
# ============================================================

def captain_score(
    player
):

    score = player[
        "agent_score"
    ]


    # Attackers benefit more from xGI
    score += (
        player[
            "expected_goal_involvement"
        ]
        *
        0.45
    )


    # Good fixture
    score += (
        player[
            "fixture_score"
        ]
        *
        0.55
    )


    # Strong starting probability
    score += (
        player[
            "starter_probability"
        ]
        /
        100
        *
        1.20
    )


    # Availability is important for captain
    score *= (
        0.70
        +
        (
            player[
                "chance_this_round"
            ]
            /
            100
        )
        *
        0.30
    )


    return score


# ============================================================
# CAPTAIN + VICE
# ============================================================

def choose_captains(
    starting_xi
):

    candidates = []

    for player in starting_xi[
        "players"
    ]:

        score = captain_score(
            player
        )

        candidates.append(
            (
                score,
                player,
            )
        )


    candidates.sort(
        key=lambda item:
        item[0],
        reverse=True,
    )


    captain = (
        candidates[0][1]
        if candidates
        else None
    )


    vice = (
        candidates[1][1]
        if len(candidates) > 1
        else None
    )


    return captain, vice


# ============================================================
# TEAM STRENGTH
# ============================================================

def team_strength(
    team
):

    # FPL exposes several strength indicators.
    #
    # We combine them into a practical model
    # for match prediction.

    overall = number(
        team.get(
            "strength",
            1000,
        ),
        1000,
    )


    attack_home = number(
        team.get(
            "strength_attack_home",
            overall,
        ),
        overall,
    )

    attack_away = number(
        team.get(
            "strength_attack_away",
            overall,
        ),
        overall,
    )


    defence_home = number(
        team.get(
            "strength_defence_home",
            overall,
        ),
        overall,
    )

    defence_away = number(
        team.get(
            "strength_defence_away",
            overall,
        ),
        overall,
    )


    return {

        "overall":
            overall,

        "attack_home":
            attack_home,

        "attack_away":
            attack_away,

        "defence_home":
            defence_home,

        "defence_away":
            defence_away,

    }


# ============================================================
# MATCH EXPECTED GOALS
# ============================================================

def match_expected_goals(
    home_team,
    away_team,
):

    home = team_strength(
        home_team
    )

    away = team_strength(
        away_team
    )


    # FPL strength values are relative.
    # Convert difference into a controlled multiplier.

    home_attack = (
        home["attack_home"]
        /
        max(
            away["defence_away"],
            1,
        )
    )


    away_attack = (
        away["attack_away"]
        /
        max(
            home["defence_home"],
            1,
        )
    )


    # Normalise around a practical football baseline.
    #
    # The exact constants are deliberately conservative;
    # we don't want absurd 6-0 predictions.

    home_xg = (
        1.35
        *
        math.sqrt(
            max(
                home_attack,
                0.20,
            )
        )
    )


    away_xg = (
        1.05
        *
        math.sqrt(
            max(
                away_attack,
                0.20,
            )
        )
    )


    # Overall strength adjustment

    strength_difference = (
        home["overall"]
        -
        away["overall"]
    )


    adjustment = clamp(
        strength_difference / 1000,
        -0.35,
        0.35,
    )


    home_xg *= (
        1
        +
        adjustment
        *
        0.25
    )


    away_xg *= (
        1
        -
        adjustment
        *
        0.15
    )


    return {

        "home":
            clamp(
                home_xg,
                0.15,
                4.50,
            ),

        "away":
            clamp(
                away_xg,
                0.10,
                3.80,
            ),

    }


# ============================================================
# MATCH SCORE MATRIX
# ============================================================

def calculate_match_probabilities(
    home_xg,
    away_xg,
):

    matrix = {}

    home_win = 0.0
    draw = 0.0
    away_win = 0.0


    for home_goals in range(
        0,
        7,
    ):

        for away_goals in range(
            0,
            7,
        ):

            probability = (

                poisson_probability(
                    home_goals,
                    home_xg,
                )

                *

                poisson_probability(
                    away_goals,
                    away_xg,
                )

            )


            score = (
                f"{home_goals}-"
                f"{away_goals}"
            )


            matrix[
                score
            ] = probability


            if home_goals > away_goals:

                home_win += probability

            elif home_goals == away_goals:

                draw += probability

            else:

                away_win += probability


    total = (
        home_win
        +
        draw
        +
        away_win
    )


    if total <= 0:

        total = 1


    home_win /= total
    draw /= total
    away_win /= total


    top_scores = sorted(
        matrix.items(),
        key=lambda item:
        item[1],
        reverse=True,
    )[:8]


    return {

        "home_win":
            home_win,

        "draw":
            draw,

        "away_win":
            away_win,

        "top_scores":
            [
                {
                    "score":
                        score,

                    "probability":
                        round(
                            probability * 100,
                            2,
                        ),
                }

                for score, probability
                in top_scores
            ],

    }


# ============================================================
# LIKELY GOAL SCORERS
# ============================================================

def calculate_goal_scorers(
    players,
    team_id,
    team_xg,
):

    candidates = [

        player

        for player in players

        if player["team_id"] == team_id

        and player["position"]
        in (
            "MID",
            "FWD",
        )

        and player[
            "chance_this_round"
        ] >= 50

        and player[
            "minutes"
        ] >= 180

    ]


    if not candidates:

        return []


    scorer_values = []


    for player in candidates:

        xg90 = player[
            "xg_per_90"
        ]


        if xg90 <= 0:

            # If xG isn't available early season,
            # use goals and threat as fallback.

            xg90 = (
                player["goals"]
                /
                max(
                    player["minutes"],
                    90,
                )
                *
                90
            )


        attacking_signal = (

            xg90 * 2.5

            +

            player[
                "threat"
            ] / 250

            +

            player[
                "expected_goal_involvement"
            ] / 8

            +

            player[
                "starter_probability"
            ] / 100

        )


        # Midfielders receive a slight assist contribution.
        attacking_signal += (
            player[
                "xa_per_90"
            ]
            *
            0.50
        )


        attacking_signal *= (
            player[
                "chance_this_round"
            ]
            /
            100
        )


        scorer_values.append(
            (
                attacking_signal,
                player,
            )
        )


    scorer_values.sort(
        key=lambda item:
        item[0],
        reverse=True,
    )


    top = scorer_values[:5]


    total = sum(
        value
        for value, player
        in top
    )


    results = []


    for value, player in top:

        if total > 0:

            relative_probability = (
                value / total
            )

        else:

            relative_probability = 0


        # This is NOT a bookmaker probability.
        # It is the model's relative scorer ranking.

        results.append({

            "player":
                player["name"],

            "team":
                player["team"],

            "position":
                player["position"],

            "model_share":
                round(
                    relative_probability * 100,
                    2,
                ),

            "xg_per_90":
                player["xg_per_90"],

            "starter_probability":
                player[
                    "starter_probability"
                ],

        })


    return results


# ============================================================
# PREDICT ALL UPCOMING FIXTURES
# ============================================================

def predict_upcoming_matches(
    fixtures,
    teams,
    players,
    current_gameweek,
):

    team_lookup = build_team_lookup(
        teams
    )


    results = []


    for fixture in fixtures:

        if fixture.get(
            "finished",
            False,
        ):

            continue


        event = fixture.get(
            "event"
        )


        if event is None:

            continue


        event = integer(
            event
        )


        if event <= current_gameweek:

            continue


        home_id = integer(
            fixture.get(
                "team_h"
            )
        )

        away_id = integer(
            fixture.get(
                "team_a"
            )
        )


        home_team = team_lookup.get(
            home_id
        )

        away_team = team_lookup.get(
            away_id
        )


        if not home_team or not away_team:

            continue


        home_name = home_team.get(
            "name",
            "Unknown",
        )

        away_name = away_team.get(
            "name",
            "Unknown",
        )


        try:

            expected = match_expected_goals(
                home_team,
                away_team,
            )


            probabilities = (
                calculate_match_probabilities(

                    expected["home"],

                    expected["away"],

                )
            )


            home_probability = (
                probabilities[
                    "home_win"
                ]
            )

            draw_probability = (
                probabilities[
                    "draw"
                ]
            )

            away_probability = (
                probabilities[
                    "away_win"
                ]
            )


            options = {

                "HOME":
                    home_probability,

                "DRAW":
                    draw_probability,

                "AWAY":
                    away_probability,

            }


            prediction = max(
                options,
                key=options.get,
            )


            confidence = (
                options[
                    prediction
                ]
                *
                100
            )


            home_scorers = (
                calculate_goal_scorers(
                    players,
                    home_id,
                    expected["home"],
                )
            )


            away_scorers = (
                calculate_goal_scorers(
                    players,
                    away_id,
                    expected["away"],
                )
            )


            results.append({

                "gameweek":
                    event,

                "fixture_id":
                    fixture.get(
                        "id"
                    ),

                "kickoff":
                    fixture.get(
                        "kickoff_time"
                    ),

                "home":
                    home_name,

                "away":
                    away_name,

                "prediction":
                    prediction,

                "confidence":
                    round(
                        confidence,
                        2,
                    ),

                "probabilities": {

                    "home_win":
                        round(
                            home_probability * 100,
                            2,
                        ),

                    "draw":
                        round(
                            draw_probability * 100,
                            2,
                        ),

                    "away_win":
                        round(
                            away_probability * 100,
                            2,
                        ),

                },

                "expected_goals": {

                    "home":
                        round(
                            expected["home"],
                            2,
                        ),

                    "away":
                        round(
                            expected["away"],
                            2,
                        ),

                },

                "most_likely_score":
                    probabilities[
                        "top_scores"
                    ][0]["score"],

                "top_scores":
                    probabilities[
                        "top_scores"
                    ],

                "likely_scorers": {

                    "home":
                        home_scorers,

                    "away":
                        away_scorers,

                },

            })


        except Exception as error:

            print(
                "Match prediction failed:",
                home_name,
                "vs",
                away_name,
                "|",
                error,
            )


    results.sort(
        key=lambda item:
        (
            item["gameweek"],
            item["confidence"],
        ),
        reverse=False,
    )


    return results


# ============================================================
# FORMAT UPCOMING FIXTURES FOR PLAYERS
# ============================================================

def make_fixture_summary(
    player,
    team_lookup,
):

    output = []


    for fixture in player[
        "upcoming_fixtures"
    ]:

        opponent = team_lookup.get(
            fixture["opponent"],
            {},
        )


        opponent_name = opponent.get(
            "short_name",
            "UNK",
        )


        if fixture["home"]:

            label = (
                "H vs "
                +
                opponent_name
            )

        else:

            label = (
                "A vs "
                +
                opponent_name
            )


        output.append({

            "gameweek":
                fixture["event"],

            "fixture":
                label,

            "difficulty":
                fixture["difficulty"],

            "kickoff":
                fixture["kickoff"],

        })


    return output


# ============================================================
# FINAL FPL REPORT
# ============================================================

def build_fpl_report(
    analysed_players,
    best_squad,
    starting_xi,
    bench,
    captain,
    vice_captain,
    gameweek_info,
    team_lookup,
):

    report = {

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "gameweek": {

            "current":
                gameweek_info[
                    "current"
                ],

            "next":
                gameweek_info[
                    "next"
                ],

        },

        "budget": {

            "maximum":
                BUDGET,

            "squad_cost":
                squad_cost(
                    best_squad
                ),

            "remaining":
                round(
                    BUDGET
                    -
                    squad_cost(
                        best_squad
                    ),
                    1,
                ),

        },

        "squad": {

            "size":
                len(best_squad),

            "players":
                best_squad,

        },

        "starting_xi": {

            "formation":
                starting_xi[
                    "formation"
                ],

            "players":
                starting_xi[
                    "players"
                ],

        },

        "bench":
            bench,

        "captain":
            captain,

        "vice_captain":
            vice_captain,

        "top_players": {

            "GK":
                sorted(
                    by_position(
                        analysed_players,
                        "GK",
                    ),
                    key=lambda p:
                    p["agent_score"],
                    reverse=True,
                )[:15],

            "DEF":
                sorted(
                    by_position(
                        analysed_players,
                        "DEF",
                    ),
                    key=lambda p:
                    p["agent_score"],
                    reverse=True,
                )[:20],

            "MID":
                sorted(
                    by_position(
                        analysed_players,
                        "MID",
                    ),
                    key=lambda p:
                    p["agent_score"],
                    reverse=True,
                )[:20],

            "FWD":
                sorted(
                    by_position(
                        analysed_players,
                        "FWD",
                    ),
                    key=lambda p:
                    p["agent_score"],
                    reverse=True,
                )[:20],

        },

    }


    # Add human-readable fixture summaries
    for section in (
        report["squad"]["players"],
        report["starting_xi"]["players"],
        report["bench"],
        report["top_players"]["GK"],
        report["top_players"]["DEF"],
        report["top_players"]["MID"],
        report["top_players"]["FWD"],
    ):

        for player in section:

            player[
                "fixture_summary"
            ] = make_fixture_summary(
                player,
                team_lookup,
            )


    return report


# ============================================================
# PRINT SQUAD
# ============================================================

def print_squad(
    report
):

    print("")
    print("=" * 60)
    print("BEST FPL SQUAD")
    print("=" * 60)

    print(
        "Budget:",
        report["budget"]["maximum"],
        "M"
    )

    print(
        "Cost:",
        report["budget"]["squad_cost"],
        "M"
    )

    print(
        "Remaining:",
        report["budget"]["remaining"],
        "M"
    )


    print("")
    print("15 PLAYERS")
    print("-" * 60)


    for player in report[
        "squad"
    ]["players"]:

        print(
            f"{player['position']:3} "
            f"{player['name']:<20} "
            f"{player['team']:<5} "
            f"£{player['price']:<5} "
            f"Score={player['agent_score']}"
        )


    print("")
    print("=" * 60)
    print("STARTING XI")
    print("=" * 60)


    print(
        "Formation:",
        report[
            "starting_xi"
        ]["formation"]
    )


    for player in report[
        "starting_xi"
    ]["players"]:

        print(
            f"{player['position']:3} "
            f"{player['name']:<20} "
            f"{player['team']:<5} "
            f"Score={player['agent_score']}"
        )


    print("")
    print("=" * 60)
    print("BENCH")
    print("=" * 60)


    for player in report[
        "bench"
    ]:

        print(
            f"{player['position']:3} "
            f"{player['name']:<20} "
            f"{player['team']:<5} "
            f"£{player['price']:<5}"
        )


    print("")
    print("=" * 60)
    print("CAPTAIN")
    print("=" * 60)


    if report["captain"]:

        print(
            report["captain"]["name"],
            "|",
            report["captain"]["team"],
        )


    print("")
    print("VICE-CAPTAIN")


    if report["vice_captain"]:

        print(
            report[
                "vice_captain"
            ]["name"],
            "|",
            report[
                "vice_captain"
            ]["team"],
        )


# ============================================================
# PRINT MATCH PREDICTIONS
# ============================================================

def print_match_predictions(
    predictions,
    limit=15,
):

    print("")
    print("=" * 60)
    print("MATCH PREDICTIONS")
    print("=" * 60)


    for prediction in predictions[:limit]:

        print("")
        print(
            f"GW{prediction['gameweek']} "
            f"{prediction['home']} "
            f"vs "
            f"{prediction['away']}"
        )


        print(
            "Prediction:",
            prediction["prediction"],
        )


        print(
            "Confidence:",
            prediction["confidence"],
            "%",
        )


        print(
            "Probabilities:",
            prediction[
                "probabilities"
            ],
        )


        print(
            "Expected goals:",
            prediction[
                "expected_goals"
            ],
        )


        print(
            "Most likely score:",
            prediction[
                "most_likely_score"
            ],
        )


        print(
            "Top scores:",
            prediction[
                "top_scores"
            ][:3],
        )


        print(
            "Likely scorers HOME:",
            [
                x["player"]
                for x
                in prediction[
                    "likely_scorers"
                ]["home"][:3]
            ],
        )


        print(
            "Likely scorers AWAY:",
            [
                x["player"]
                for x
                in prediction[
                    "likely_scorers"
                ]["away"][:3]
            ],
        )


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    filename,
    data,
):

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("FPL AUTONOMOUS AGENT")
    print("DEEP PLAYER + FIXTURE + MATCH ANALYSIS")
    print("=" * 60)
    print("")


    # --------------------------------------------------------
    # LOAD DATABASE
    # --------------------------------------------------------

    data = load_fpl_database()


    players = data[
        "players"
    ]

    events = data[
        "events"
    ]

    teams = data[
        "teams"
    ]

    fixtures = data[
        "fixtures"
    ]


    # --------------------------------------------------------
    # GAMEWEEK
    # --------------------------------------------------------

    gameweek_info = get_gameweek_info(
        events
    )


    current_gameweek = gameweek_info[
        "current"
    ]

    next_gameweek = gameweek_info[
        "next"
    ]


    print("")
    print(
        "Current GW:",
        current_gameweek,
    )

    print(
        "Next GW:",
        next_gameweek,
    )


    # --------------------------------------------------------
    # LOOKUPS
    # --------------------------------------------------------

    team_lookup = build_team_lookup(
        teams
    )


    fixture_map = build_fixture_map(
        fixtures
    )


    # --------------------------------------------------------
    # PLAYER ANALYSIS
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("ANALYSING PLAYERS")
    print("=" * 60)


    analysed_players = build_player_pool(
        players,
        team_lookup,
        fixture_map,
        current_gameweek,
    )


    print(
        "Analysed:",
        len(
            analysed_players
        ),
        "players"
    )


    # --------------------------------------------------------
    # BEST SQUAD
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("BUILDING £100M SQUAD")
    print("=" * 60)


    best_squad = build_best_squad(
        analysed_players
    )


    if not best_squad:

        raise RuntimeError(
            "Unable to build valid £100M squad."
        )


    # --------------------------------------------------------
    # STARTING XI
    # --------------------------------------------------------

    starting_xi = build_starting_xi(
        best_squad
    )


    if not starting_xi:

        raise RuntimeError(
            "Unable to build starting XI."
        )


    # --------------------------------------------------------
    # BENCH
    # --------------------------------------------------------

    bench = build_bench(
        best_squad,
        starting_xi,
    )


    # --------------------------------------------------------
    # CAPTAIN
    # --------------------------------------------------------

    captain, vice_captain = choose_captains(
        starting_xi
    )


    # --------------------------------------------------------
    # FPL REPORT
    # --------------------------------------------------------

    report = build_fpl_report(

        analysed_players,

        best_squad,

        starting_xi,

        bench,

        captain,

        vice_captain,

        gameweek_info,

        team_lookup,

    )


    # --------------------------------------------------------
    # MATCH PREDICTIONS
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("PREDICTING UPCOMING MATCHES")
    print("=" * 60)


    predictions = predict_upcoming_matches(

        fixtures,

        teams,

        analysed_players,

        current_gameweek,

    )


    # --------------------------------------------------------
    # SAVE EVERYTHING
    # --------------------------------------------------------

    full_output = {

        "agent": {

            "name":
                "FPL Autonomous Agent",

            "version":
                "2.0",

            "generated_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

        },

        "team_id":
            TEAM_ID,

        "gameweek":
            gameweek_info,

        "fpl_report":
            report,

        "match_predictions":
            predictions,

        "analysed_players":
            analysed_players,

    }


    save_json(
        "fpl_data.json",
        full_output,
    )


    # --------------------------------------------------------
    # HUMAN OUTPUT
    # --------------------------------------------------------

    print_squad(
        report
    )


    print_match_predictions(
        predictions
    )


    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("AGENT FINISHED")
    print("=" * 60)


    print(
        "Gameweek:",
        next_gameweek,
    )

    print(
        "Squad cost:",
        report[
            "budget"
        ]["squad_cost"],
        "M",
    )

    print(
        "Remaining:",
        report[
            "budget"
        ]["remaining"],
        "M",
    )


    if captain:

        print(
            "Captain:",
            captain["name"],
        )


    if vice_captain:

        print(
            "Vice-Captain:",
            vice_captain["name"],
        )


    print(
        "Matches predicted:",
        len(predictions),
    )


    print(
        "Output:",
        "fpl_data.json",
    )


    print("")
    print(
        "Ready for next stage."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print("")
        print("=" * 60)
        print("AGENT ERROR")
        print("=" * 60)

        print(
            str(error)
        )

        print("")
        print(
            "The program stopped safely."
        )

        raise
