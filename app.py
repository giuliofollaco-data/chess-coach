import datetime
import io
import chess
import chess.pgn
import requests
import json
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Active CORS pour toutes les routes

# --- CHARGEMENT DE LA CONFIGURATION ---
try:
    with open("config.json", "r", encoding="utf-8") as file:
        config = json.load(file)
except FileNotFoundError:
    config = {"username": "PseudoParDefaut", "email": "contact@example.com"}

USERNAME = config.get("username")
EMAIL = config.get("email")
HEADERS = {"User-Agent": f"ChessCoachApp/1.0 (contact: {EMAIL})"}

# Variable globale pour stocker les parties en mémoire vive
ALL_LOADED_GAMES = []


def get_games_for_month(username, year, month):
    url = f"https://api.chess.com/pub/player/{username}/games/{year}/{month:02d}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("games", [])
    return []


def get_recent_games(username, days=30):
    now = datetime.datetime.now()
    all_games = []
    months_to_check = {now.month: now.year}
    if now.day < days:
        prev = now - datetime.timedelta(days=days)
        months_to_check[prev.month] = prev.year

    for m, y in months_to_check.items():
        all_games.extend(get_games_for_month(username, y, m))
    return all_games


def filter_games(games, days=None, target_date=None):
    if target_date is not None:
        filtered = []
        for g in games:
            end_time = g.get("end_time", 0)
            if end_time:
                g_date = datetime.date.fromtimestamp(end_time)
                if isinstance(target_date, str):
                    if g_date.strftime("%Y-%m-%d") == target_date:
                        filtered.append(g)
                elif g_date == target_date:
                    filtered.append(g)
        return filtered
    elif days is not None:
        now = datetime.datetime.now()
        cutoff_timestamp = (now - datetime.timedelta(days=days)).timestamp()
        return [g for g in games if g.get("end_time", 0) >= cutoff_timestamp]
    return games


def get_game_win_stats(games, username):
    white_games = 0
    white_wins = 0
    black_games = 0
    black_wins = 0

    for game in games:
        white_player = game.get("white", {})
        black_player = game.get("black", {})

        is_user_white = white_player.get("username", "").lower() == username.lower()
        is_user_black = black_player.get("username", "").lower() == username.lower()

        if is_user_white:
            white_games += 1
            if white_player.get("result", "") == "win":
                white_wins += 1
        elif is_user_black:
            black_games += 1
            if black_player.get("result", "") == "win":
                black_wins += 1

    white_win_pct = (white_wins / white_games * 100) if white_games > 0 else 0.0
    black_win_pct = (black_wins / black_games * 100) if black_games > 0 else 0.0

    total_games = white_games + black_games
    total_wins = white_wins + black_wins
    total_win_pct = (total_wins / total_games * 100) if total_games > 0 else 0.0

    return {
        "white_games": white_games,
        "white_wins": white_wins,
        "white_win_pct": round(white_win_pct, 1),
        "black_games": black_games,
        "black_wins": black_wins,
        "black_win_pct": round(black_win_pct, 1),
        "total_games": total_games,
        "total_wins": total_wins,
        "total_win_pct": round(total_win_pct, 1),
    }


def to_french_san(eng_san_str):
    mapping = {"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"}
    return "".join(mapping.get(char, char) for char in eng_san_str)


def get_opponent_move_stats(games, current_fen):
    board_target = chess.Board(current_fen)
    target_key = " ".join(board_target.fen().split()[:4])
    target_turn = board_target.turn

    move_counts = {}
    total_matches = 0

    for game in games:
        if "pgn" not in game:
            continue

        is_user_white = (
            game.get("white", {}).get("username", "").lower() == USERNAME.lower()
        )
        is_user_black = (
            game.get("black", {}).get("username", "").lower() == USERNAME.lower()
        )

        if target_turn == chess.WHITE and is_user_white:
            continue
        if target_turn == chess.BLACK and is_user_black:
            continue

        pgn_text = game["pgn"]
        pgn_io = io.StringIO(pgn_text)
        chess_game = chess.pgn.read_game(pgn_io)

        if not chess_game:
            continue

        board = chess_game.board()
        for move in chess_game.mainline_moves():
            current_key = " ".join(board.fen().split()[:4])
            if current_key == target_key:
                standard_san = board.san(move)
                french_san = to_french_san(standard_san)
                move_counts[french_san] = move_counts.get(french_san, 0) + 1
                total_matches += 1
                break
            board.push(move)

    stats = []
    for m, count in move_counts.items():
        pct = (count / total_matches) * 100
        stats.append({"move": m, "count": count, "pct": round(pct, 1)})

    return sorted(stats, key=lambda x: x["count"], reverse=True)


# --- ROUTES DE L'API WEB ---


@app.route("/api/init", methods=["GET"])
def init_games():
    """Charge les parties en mémoire au démarrage"""
    global ALL_LOADED_GAMES
    if not ALL_LOADED_GAMES:
        print(f"Téléchargement des parties pour {USERNAME}...")
        ALL_LOADED_GAMES = get_recent_games(USERNAME, days=30)
    return jsonify({"status": "success", "games_count": len(ALL_LOADED_GAMES)})


@app.route("/api/stats", methods=["POST"])
def get_stats():
    """Reçoit un FEN et des filtres du frontend, et renvoie les stats de coups"""
    data = request.json or {}
    current_fen = data.get("fen", chess.STARTING_FEN)
    days = data.get("days")
    date = data.get("date")

    filtered = filter_games(ALL_LOADED_GAMES, days=days, target_date=date)
    stats = get_opponent_move_stats(filtered, current_fen)

    return jsonify({"stats": stats})


@app.route("/api/win-stats", methods=["POST"])
def get_win_stats_endpoint():
    """Renvoie les statistiques de victoire pour les filtres donnés"""
    data = request.json or {}
    days = data.get("days")
    date = data.get("date")

    filtered = filter_games(ALL_LOADED_GAMES, days=days, target_date=date)
    stats = get_game_win_stats(filtered, USERNAME)

    return jsonify(stats)


@app.route("/api/games-by-day", methods=["GET"])
def get_games_by_day():
    """Compte le nombre de parties jouées chaque jour pour le calendrier"""
    counts = {}
    for g in ALL_LOADED_GAMES:
        end_time = g.get("end_time", 0)
        if end_time:
            g_date = datetime.date.fromtimestamp(end_time)
            date_str = g_date.strftime("%Y-%m-%d")
            counts[date_str] = counts.get(date_str, 0) + 1
    return jsonify(counts)


if __name__ == "__main__":
    # Lance l'API sur http://127.0.0.1:5000
    app.run(debug=True, port=5000)
