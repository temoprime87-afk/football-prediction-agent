import os
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ============================================================
# FOOTBALL PREDICTION AGENT
# Version 1.0
# ============================================================

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")

BASE_URL = "https://api.football-data.org/v4"

LAST_MATCHES = 10
MAX_GOALS = 6

COMPETITIONS = {
    "PL": "Premier League",
    "PD": "La Liga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
}


# ============================================================
# API
# ============================================================

def get_json(url):

    if not API_KEY:
        raise RuntimeError(
            "FOOTBALL_DATA_API_KEY is not configured."
        )

    request = urllib.request.Request(
        url,
        headers={
            "X-Auth-Token": API_KEY,
            "User-Agent": "FootballPredictionAgent/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:

        body = error.read().decode(
            "utf-8",
            errors="ignore"
        )

        raise RuntimeError(
            f"HTTP {error.code}: {body}"
        )

    except urllib.error.URLError as error:

        raise RuntimeError(
            f"Network error: {error.reason}"
        )


# ============================================================
# HELPERS
# ============================================================

def safe_float(value, default=0.0):

    try:
        return float(value)
    except:
        return default


def clamp(value, minimum, maximum):

    return max(
        minimum,
        min(maximum, value)
    )


def poisson_probability(
    goals,
    expected_goals
):

    expected_goals = max(
        expected_goals,
        0.01
    )

    return (
        math.exp(-expected_goals)
        *
        expected_goals ** goals
        /
        math.factorial(goals)
    )


# ============================================================
# GET FINISHED MATCHES
# ============================================================

def get_team_matches(
    competition,
    team_id
):

    url = (
        f"{BASE_URL}/teams/"
        f"{team_id}/matches"
        f"?competitions={competition}"
        f"&status=FINISHED"
        f"&limit={LAST_MATCHES}"
    )

    data = get_json(url)

    return data.get(
        "matches",
        []
    )


# ============================================================
# TEAM STATISTICS
# ============================================================

def calculate_team_stats(
    matches,
    team_id
):

    if not matches:

        return {
            "matches": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goals_for_avg": 0,
            "goals_against_avg": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "points": 0,
            "points_per_match": 0,
            "win_rate": 0,
        }


    goals_for = 0
    goals_against = 0

    wins = 0
    draws = 0
    losses = 0

    points = 0


    for match in matches:

        home_id = match[
            "homeTeam"
        ]["id"]

        away_id = match[
            "awayTeam"
        ]["id"]

        score = match.get(
            "score",
            {}
        ).get(
            "fullTime",
            {}
        )

        home_goals = safe_float(
            score.get("home")
        )

        away_goals = safe_float(
            score.get("away")
        )


        if team_id == home_id:

            gf = home_goals
            ga = away_goals

        else:

            gf = away_goals
            ga = home_goals


        goals_for += gf
        goals_against += ga


        if gf > ga:

            wins += 1
            points += 3

        elif gf == ga:

            draws += 1
            points += 1

        else:

            losses += 1


    count = len(matches)


    return {

        "matches":
            count,

        "goals_for":
            goals_for,

        "goals_against":
            goals_against,

        "goals_for_avg":
            goals_for / count,

        "goals_against_avg":
            goals_against / count,

        "wins":
            wins,

        "draws":
            draws,

        "losses":
            losses,

        "points":
            points,

        "points_per_match":
            points / count,

        "win_rate":
            wins / count,

    }


# ============================================================
# HOME / AWAY STATISTICS
# ============================================================

def calculate_home_away_stats(
    matches,
    team_id
):

    home_games = 0
    away_games = 0

    home_for = 0
    home_against = 0

    away_for = 0
    away_against = 0


    for match in matches:

        home_id = match[
            "homeTeam"
        ]["id"]

        away_id = match[
            "awayTeam"
        ]["id"]

        score = match.get(
            "score",
            {}
        ).get(
            "fullTime",
            {}
        )

        home_goals = safe_float(
            score.get("home")
        )

        away_goals = safe_float(
            score.get("away")
        )


        if team_id == home_id:

            home_games += 1

            home_for += home_goals
            home_against += away_goals


        elif team_id == away_id:

            away_games += 1

            away_for += away_goals
            away_against += home_goals


    return {

        "home_games":
            home_games,

        "away_games":
            away_games,

        "home_goals_for_avg":
            (
                home_for / home_games
                if home_games
                else 0
            ),

        "home_goals_against_avg":
            (
                home_against / home_games
                if home_games
                else 0
            ),

        "away_goals_for_avg":
            (
                away_for / away_games
                if away_games
                else 0
            ),

        "away_goals_against_avg":
            (
                away_against / away_games
                if away_games
                else 0
            ),
    }


# ============================================================
# ELO
# ============================================================

def calculate_elo(
    matches,
    team_id,
    initial_elo=1500
):

    elo = initial_elo

    K = 25


    # Oldest -> newest
    matches = list(
        reversed(matches)
    )


    for match in matches:

        home_id = match[
            "homeTeam"
        ]["id"]

        away_id = match[
            "awayTeam"
        ]["id"]

        score = match.get(
            "score",
            {}
        ).get(
            "fullTime",
            {}
        )

        home_goals = safe_float(
            score.get("home")
        )

        away_goals = safe_float(
            score.get("away")
        )


        if home_goals > away_goals:

            result = 1.0

        elif home_goals == away_goals:

            result = 0.5

        else:

            result = 0.0


        if team_id == home_id:

            opponent_elo = 1500

            expected = (
                1 /
                (
                    1 +
                    10 ** (
                        (opponent_elo - elo)
                        / 400
                    )
                )
            )

            elo += K * (
                result - expected
            )


        elif team_id == away_id:

            opponent_elo = 1500

            expected = (
                1 /
                (
                    1 +
                    10 ** (
                        (opponent_elo - elo)
                        / 400
                    )
                )
            )

            away_result = 1 - result

            elo += K * (
                away_result - expected
            )


    return elo


# ============================================================
# EXPECTED GOALS
# ============================================================

def calculate_expected_goals(
    home_stats,
    away_stats,
    home_split,
    away_split,
    home_elo,
    away_elo
):

    # --------------------------------------------------------
    # HOME TEAM ATTACK
    # --------------------------------------------------------

    home_attack = (
        home_split[
            "home_goals_for_avg"
        ]
    )

    home_defence = (
        home_split[
            "home_goals_against_avg"
        ]
    )


    # --------------------------------------------------------
    # AWAY TEAM ATTACK
    # --------------------------------------------------------

    away_attack = (
        away_split[
            "away_goals_for_avg"
        ]
    )

    away_defence = (
        away_split[
            "away_goals_against_avg"
        ]
    )


    # --------------------------------------------------------
    # RECENT FORM
    # --------------------------------------------------------

    home_form = (
        home_stats[
            "goals_for_avg"
        ] * 0.55
        +
        (
            1 /
            (
                1 +
                home_stats[
                    "goals_against_avg"
                ]
            )
        ) * 0.45
    )


    away_form = (
        away_stats[
            "goals_for_avg"
        ] * 0.55
        +
        (
            1 /
            (
                1 +
                away_stats[
                    "goals_against_avg"
                ]
            )
        ) * 0.45
    )


    # --------------------------------------------------------
    # BASE EXPECTED GOALS
    # --------------------------------------------------------

    home_xg = (
        home_attack * 0.45
        +
        away_defence * 0.35
        +
        home_form * 0.20
    )


    away_xg = (
        away_attack * 0.45
        +
        home_defence * 0.35
        +
        away_form * 0.20
    )


    # --------------------------------------------------------
    # HOME ADVANTAGE
    # --------------------------------------------------------

    home_xg *= 1.10


    # --------------------------------------------------------
    # ELO DIFFERENCE
    # --------------------------------------------------------

    elo_difference = (
        home_elo - away_elo
    )

    elo_factor = clamp(
        elo_difference / 400,
        -0.5,
        0.5
    )


    home_xg *= (
        1 + elo_factor * 0.12
    )

    away_xg *= (
        1 - elo_factor * 0.08
    )


    # --------------------------------------------------------
    # FORM DIFFERENCE
    # --------------------------------------------------------

    points_difference = (
        home_stats[
            "points_per_match"
        ]
        -
        away_stats[
            "points_per_match"
        ]
    )


    points_factor = clamp(
        points_difference / 3,
        -0.5,
        0.5
    )


    home_xg *= (
        1 + points_factor * 0.08
    )

    away_xg *= (
        1 - points_factor * 0.05
    )


    return {

        "home":
            clamp(
                home_xg,
                0.10,
                4.50
            ),

        "away":
            clamp(
                away_xg,
                0.10,
                4.50
            ),

    }


# ============================================================
# SCORE MATRIX
# ============================================================

def build_score_matrix(
    home_xg,
    away_xg
):

    matrix = {}

    home_win = 0
    draw = 0
    away_win = 0


    for home_goals in range(
        MAX_GOALS + 1
    ):

        for away_goals in range(
            MAX_GOALS + 1
        ):

            probability = (

                poisson_probability(
                    home_goals,
                    home_xg
                )

                *

                poisson_probability(
                    away_goals,
                    away_xg
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


    return {

        "matrix":
            matrix,

        "home_win":
            home_win / total,

        "draw":
            draw / total,

        "away_win":
            away_win / total,

    }


# ============================================================
# BEST SCORE
# ============================================================

def get_best_score(
    matrix
):

    return max(
        matrix,
        key=matrix.get
    )


# ============================================================
# PREDICT ONE MATCH
# ============================================================

def predict_match(
    home_name,
    away_name,
    home_id,
    away_id,
    competition
):

    print("")
    print(
        f"Analysing: "
        f"{home_name} vs {away_name}"
    )


    # --------------------------------------------------------
    # HISTORICAL DATA
    # --------------------------------------------------------

    home_matches = get_team_matches(
        competition,
        home_id
    )

    away_matches = get_team_matches(
        competition,
        away_id
    )


    if not home_matches:
        raise RuntimeError(
            f"No data for {home_name}"
        )

    if not away_matches:
        raise RuntimeError(
            f"No data for {away_name}"
        )


    # --------------------------------------------------------
    # TEAM STATS
    # --------------------------------------------------------

    home_stats = (
        calculate_team_stats(
            home_matches,
            home_id
        )
    )

    away_stats = (
        calculate_team_stats(
            away_matches,
            away_id
        )
    )


    # --------------------------------------------------------
    # HOME/AWAY
    # --------------------------------------------------------

    home_split = (
        calculate_home_away_stats(
            home_matches,
            home_id
        )
    )

    away_split = (
        calculate_home_away_stats(
            away_matches,
            away_id
        )
    )


    # --------------------------------------------------------
    # ELO
    # --------------------------------------------------------

    home_elo = calculate_elo(
        home_matches,
        home_id
    )

    away_elo = calculate_elo(
        away_matches,
        away_id
    )


    # --------------------------------------------------------
    # EXPECTED GOALS
    # --------------------------------------------------------

    expected_goals = (
        calculate_expected_goals(

            home_stats,

            away_stats,

            home_split,

            away_split,

            home_elo,

            away_elo

        )
    )


    home_xg = expected_goals[
        "home"
    ]

    away_xg = expected_goals[
        "away"
    ]


    # --------------------------------------------------------
    # SCORE MATRIX
    # --------------------------------------------------------

    score_data = build_score_matrix(
        home_xg,
        away_xg
    )


    matrix = score_data[
        "matrix"
    ]


    best_score = get_best_score(
        matrix
    )


    # --------------------------------------------------------
    # RESULT PROBABILITIES
    # --------------------------------------------------------

    home_probability = (
        score_data[
            "home_win"
        ]
    )

    draw_probability = (
        score_data[
            "draw"
        ]
    )

    away_probability = (
        score_data[
            "away_win"
        ]
    )


    probabilities = {

        "home_win":
            round(
                home_probability * 100,
                2
            ),

        "draw":
            round(
                draw_probability * 100,
                2
            ),

        "away_win":
            round(
                away_probability * 100,
                2
            ),

    }


    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    result_map = {

        "HOME":
            home_probability,

        "DRAW":
            draw_probability,

        "AWAY":
            away_probability,

    }


    prediction = max(
        result_map,
        key=result_map.get
    )


    confidence = (
        result_map[
            prediction
        ] * 100
    )


    # --------------------------------------------------------
    # TOP SCORES
    # --------------------------------------------------------

    top_scores = sorted(
        matrix.items(),
        key=lambda item: item[1],
        reverse=True
    )[:5]


    top_scores = [

        {
            "score":
                score,

            "probability":
                round(
                    probability * 100,
                    2
                ),
        }

        for score, probability
        in top_scores

    ]


    return {

        "match": {

            "home":
                home_name,

            "away":
                away_name,

            "competition":
                competition,

        },

        "prediction":
            prediction,

        "probabilities":
            probabilities,

        "confidence":
            round(
                confidence,
                2
            ),

        "expected_goals": {

            "home":
                round(
                    home_xg,
                    2
                ),

            "away":
                round(
                    away_xg,
                    2
                ),

        },

        "most_likely_score":
            best_score,

        "top_scores":
            top_scores,

        "model_data": {

            "home_elo":
                round(
                    home_elo,
                    1
                ),

            "away_elo":
                round(
                    away_elo,
                    1
                ),

            "home_form":
                home_stats,

            "away_form":
                away_stats,

        },

    }


# ============================================================
# UPCOMING MATCHES
# ============================================================

def get_upcoming_matches(
    competition
):

    url = (
        f"{BASE_URL}/competitions/"
        f"{competition}/matches"
        f"?status=SCHEDULED"
    )

    data = get_json(url)

    return data.get(
        "matches",
        []
    )


# ============================================================
# ANALYSE COMPETITION
# ============================================================

def analyse_competition(
    code
):

    matches = get_upcoming_matches(
        code
    )

    predictions = []


    for match in matches:

        home = match.get(
            "homeTeam",
            {}
        )

        away = match.get(
            "awayTeam",
            {}
        )


        home_id = home.get("id")
        away_id = away.get("id")


        if not home_id or not away_id:
            continue


        try:

            prediction = predict_match(

                home.get(
                    "name",
                    "Unknown"
                ),

                away.get(
                    "name",
                    "Unknown"
                ),

                home_id,

                away_id,

                code

            )


            prediction[
                "date"
            ] = match.get(
                "utcDate"
            )

            prediction[
                "match_id"
            ] = match.get(
                "id"
            )


            predictions.append(
                prediction
            )


        except Exception as error:

            print(
                "Skipped match:",
                error
            )


    return predictions


# ============================================================
# CLEAN USER OUTPUT
# ============================================================

def print_final_prediction(
    prediction
):

    match = prediction[
        "match"
    ]

    probabilities = prediction[
        "probabilities"
    ]


    print("")
    print(
        "========================================"
    )

    print(
        "          FINAL PREDICTION"
    )

    print(
        "========================================"
    )

    print("")
    print(
        match["home"],
        "vs",
        match["away"]
    )

    print("")

    print(
        "Prediction:",
        prediction["prediction"]
    )

    print(
        "Home:",
        probabilities["home_win"],
        "%"
    )

    print(
        "Draw:",
        probabilities["draw"],
        "%"
    )

    print(
        "Away:",
        probabilities["away_win"],
        "%"
    )

    print("")

    print(
        "Expected score:",
        prediction[
            "most_likely_score"
        ]
    )

    print(
        "Expected goals:",
        prediction[
            "expected_goals"
        ]
    )

    print(
        "Confidence:",
        prediction[
            "confidence"
        ],
        "%"
    )

    print("")
    print(
        "Top possible scores:"
    )

    for item in prediction[
        "top_scores"
    ]:

        print(
            item["score"],
            "->",
            item["probability"],
            "%"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print(
        "========================================"
    )

    print(
        "     FOOTBALL PREDICTION AGENT v1"
    )

    print(
        "========================================"
    )


    if not API_KEY:

        print("")
        print(
            "ERROR: Missing API key."
        )

        print(
            "Add FOOTBALL_DATA_API_KEY "
            "to GitHub Actions secrets."
        )

        return


    all_predictions = []


    for code, name in COMPETITIONS.items():

        print("")
        print(
            "Loading:",
            name
        )

        try:

            predictions = (
                analyse_competition(
                    code
                )
            )

            all_predictions.extend(
                predictions
            )

        except Exception as error:

            print(
                name,
                "failed:",
                error
            )


    # --------------------------------------------------------
    # SAVE FULL DATA
    # --------------------------------------------------------

    output = {

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "predictions":
            all_predictions,

    }


    with open(
        "predictions.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )


    # --------------------------------------------------------
    # SHOW FIRST PREDICTIONS
    # --------------------------------------------------------

    for prediction in all_predictions[:10]:

        print_final_prediction(
            prediction
        )


    print("")
    print(
        "========================================"
    )

    print(
        "DONE"
    )

    print(
        "Matches analysed:",
        len(all_predictions)
    )

    print(
        "Saved:",
        "predictions.json"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()
