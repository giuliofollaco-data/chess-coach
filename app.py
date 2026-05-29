import datetime
import io
import sys
import chess
import chess.pgn  # Parser officiel ultra-rapide
import pygame
import requests
import json

# --- CHARGEMENT DE LA CONFIGURATION ---
try:
    with open("config.json", "r", encoding="utf-8") as file:
        config = json.load(file)
except FileNotFoundError:
    print("Erreur : Le fichier config.json est introuvable.")
    config = {"username": "PseudoParDefaut", "email": "contact@example.com"}

# --- CONFIGURATION & API CHESS.COM ---
USERNAME = config.get("username")
EMAIL = config.get("email")

HEADERS = {"User-Agent": f"ChessCoachApp/1.0 (contact: {EMAIL})"}

# Dimensions de la fenêtre
BOARD_WIDTH, BOARD_HEIGHT = 600, 600
SIDE_PANEL_WIDTH = 250
WIDTH = BOARD_WIDTH + SIDE_PANEL_WIDTH
HEIGHT = BOARD_HEIGHT
SQ_SIZE = BOARD_WIDTH // 8

COLORS = [
    pygame.Color("#eeeed2"),
    pygame.Color("#769656"),
]  # [Cases Claires, Cases Sombres]
PIECE_TO_NAME = {
    "P": "wp",
    "R": "wr",
    "N": "wn",
    "B": "wb",
    "Q": "wq",
    "K": "wk",
    "p": "bp",
    "r": "br",
    "n": "bn",
    "b": "bb",
    "q": "bq",
    "k": "bk",
}


# --- TRADUCTION DE LA NOTATION EN FRANÇAIS ---
def to_french_san(eng_san_str):
    mapping = {"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"}
    return "".join(mapping.get(char, char) for char in eng_san_str)


# --- REQUISITIONS API ---
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


# --- FILTRE LOCAL & STATS OPTIMISÉES ---
def filter_games(games, days=None, target_date=None):
    if target_date is not None:
        filtered = []
        for g in games:
            end_time = g.get("end_time", 0)
            if end_time:
                g_date = datetime.date.fromtimestamp(end_time)
                if g_date == target_date:
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
        "white_win_pct": white_win_pct,
        "black_games": black_games,
        "black_wins": black_wins,
        "black_win_pct": black_win_pct,
        "total_games": total_games,
        "total_wins": total_wins,
        "total_win_pct": total_win_pct,
    }


def get_opponent_move_stats(games, current_fen):
    """Analyse rapide et sécurisée des PGN Chess.com"""
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

        # Utilisation du parser d'échecs natif pour éviter les boucles infinies sur le texte brut
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
        stats.append((m, count, pct))

    return sorted(stats, key=lambda x: x[1], reverse=True)


# --- GRAPHISMES & INTERFACE ---
_ORIGINAL_BOARD_IMG = None
_ORIGINAL_PIECES_IMAGES = {}
_ASSETS_LOADED = False


def load_assets():
    global _ORIGINAL_BOARD_IMG, _ORIGINAL_PIECES_IMAGES, _ASSETS_LOADED

    if not _ASSETS_LOADED:
        try:
            _ORIGINAL_BOARD_IMG = pygame.image.load("./images/boards/green.png")
        except (pygame.error, FileNotFoundError):
            _ORIGINAL_BOARD_IMG = None

        for symbol, name in PIECE_TO_NAME.items():
            path = f"./images/pieces/{name}.png"
            try:
                _ORIGINAL_PIECES_IMAGES[symbol] = pygame.image.load(path)
            except (pygame.error, FileNotFoundError):
                _ORIGINAL_PIECES_IMAGES[symbol] = None
        _ASSETS_LOADED = True

    board_img = None
    pieces_images = {}

    if _ORIGINAL_BOARD_IMG:
        board_img = pygame.transform.scale(
            _ORIGINAL_BOARD_IMG, (BOARD_WIDTH, BOARD_HEIGHT)
        )

    for symbol, img in _ORIGINAL_PIECES_IMAGES.items():
        if img:
            pieces_images[symbol] = pygame.transform.scale(img, (SQ_SIZE, SQ_SIZE))
        else:
            pieces_images[symbol] = None

    return board_img, pieces_images


def draw_board(screen, board_img, board_flipped):
    if board_img:
        if board_flipped:
            screen.blit(pygame.transform.rotate(board_img, 180), (0, 0))
        else:
            screen.blit(board_img, (0, 0))
    else:
        for square in chess.SQUARES:
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            col = 7 - file if board_flipped else file
            row = rank if board_flipped else 7 - rank
            color = COLORS[0] if chess.square_light(square) else COLORS[1]
            pygame.draw.rect(
                screen,
                color,
                pygame.Rect(col * SQ_SIZE, row * SQ_SIZE, SQ_SIZE, SQ_SIZE),
            )


def draw_pieces(
    screen, board, pieces_images, board_flipped, dragged_piece=None, dragged_pos=None
):
    fallback_symbols = {
        "P": "♙",
        "R": "♖",
        "N": "♘",
        "B": "♗",
        "Q": "♕",
        "K": "♔",
        "p": "♟",
        "r": "♜",
        "n": "♞",
        "b": "♝",
        "q": "♛",
        "k": "♚",
    }
    font_size = int(SQ_SIZE * 0.8)
    font = pygame.font.SysFont("Segoe UI Symbol", font_size)

    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            symbol = piece.symbol()
            # Correction de la condition booléenne pour la case 0 (A1)
            if dragged_piece is not None and square == dragged_piece:
                continue

            col = chess.square_file(square)
            row = chess.square_rank(square)

            if board_flipped:
                col = 7 - col
            else:
                row = 7 - row

            x, y = col * SQ_SIZE, row * SQ_SIZE

            img = pieces_images.get(symbol)
            if img:
                screen.blit(img, (x, y))
            else:
                text_surface = font.render(fallback_symbols[symbol], True, (0, 0, 0))
                text_rect = text_surface.get_rect(center=(x + SQ_SIZE // 2, y + SQ_SIZE // 2))
                screen.blit(text_surface, text_rect)

    # Correction de la condition booléenne pour dessiner la pièce traînée (A1 incluse)
    if dragged_piece is not None and dragged_pos:
        piece = board.piece_at(dragged_piece)
        symbol = piece.symbol()
        img = pieces_images.get(symbol)
        if img:
            screen.blit(
                img, (dragged_pos[0] - SQ_SIZE // 2, dragged_pos[1] - SQ_SIZE // 2)
            )
        else:
            text_surface = font.render(fallback_symbols[symbol], True, (0, 0, 0))
            text_rect = text_surface.get_rect(center=dragged_pos)
            screen.blit(text_surface, text_rect)


# --- PANNEAU LATÉRAL ---
BTN_1J = pygame.Rect(BOARD_WIDTH + 15, 55, 65, 30)
BTN_7J = pygame.Rect(BOARD_WIDTH + 90, 55, 65, 30)
BTN_30J = pygame.Rect(BOARD_WIDTH + 165, 55, 65, 30)
BTN_FLIP = pygame.Rect(BOARD_WIDTH + 15, 95, 215, 30)


def draw_side_panel(
    screen, stats, selected_days, selected_date=None, games_per_day=None, win_stats=None
):
    scale = BOARD_WIDTH / 600.0

    pygame.draw.rect(
        screen,
        pygame.Color("#262522"),
        pygame.Rect(BOARD_WIDTH, 0, SIDE_PANEL_WIDTH, BOARD_HEIGHT),
    )
    pygame.draw.line(
        screen,
        pygame.Color("#312e2b"),
        (BOARD_WIDTH, 0),
        (BOARD_WIDTH, BOARD_HEIGHT),
        max(1, int(3 * scale)),
    )

    title_font = pygame.font.SysFont("Arial", int(16 * scale), bold=True)
    btn_font = pygame.font.SysFont("Arial", int(14 * scale), bold=True)
    text_font = pygame.font.SysFont("Arial", int(15 * scale), bold=True)

    title_surface = title_font.render("OPTIONS", True, pygame.Color("#ffffff"))
    screen.blit(title_surface, (BOARD_WIDTH + int(20 * scale), int(20 * scale)))

    buttons = [(BTN_1J, "1 J", 1), (BTN_7J, "7 J", 7), (BTN_30J, "30 J", 30)]
    for rect, label, days in buttons:
        is_active = selected_days == days
        bg_color = pygame.Color("#81b64c") if is_active else pygame.Color("#312e2b")
        text_color = pygame.Color("#ffffff") if is_active else pygame.Color("#989795")
        pygame.draw.rect(screen, bg_color, rect, border_radius=max(1, int(4 * scale)))
        btn_text = btn_font.render(label, True, text_color)
        screen.blit(btn_text, btn_text.get_rect(center=rect.center))

    pygame.draw.rect(screen, pygame.Color("#312e2b"), BTN_FLIP, border_radius=max(1, int(4 * scale)))
    flip_text = btn_font.render("Tourner l'échiquier", True, pygame.Color("#ffffff"))
    screen.blit(flip_text, flip_text.get_rect(center=BTN_FLIP.center))

    # --- MINI CALENDRIER INTERACTIF ---
    cal_title_font = pygame.font.SysFont("Arial", int(13 * scale), bold=True)
    cal_day_font = pygame.font.SysFont("Arial", int(11 * scale))
    cal_header_font = pygame.font.SysFont("Arial", int(11 * scale), bold=True)

    cal_title = cal_title_font.render(
        "CALENDRIER (30 derniers jours)", True, pygame.Color("#ffffff")
    )
    screen.blit(cal_title, (BOARD_WIDTH + int(15 * scale), int(135 * scale)))

    # En-têtes de colonnes (jours de la semaine en français)
    headers = ["L", "M", "M", "J", "V", "S", "D"]
    CALENDAR_X = BOARD_WIDTH + int(48 * scale)
    GRID_START_Y = int(168 * scale)
    CELL_SIZE = int(22 * scale)
    CELL_GAP = int(20 * scale)
    HALF_CELL = CELL_GAP // 2

    for i, h in enumerate(headers):
        h_surf = cal_header_font.render(h, True, pygame.Color("#7d7c7a"))
        h_rect = h_surf.get_rect(center=(CALENDAR_X + i * CELL_SIZE + HALF_CELL, int(158 * scale)))
        screen.blit(h_surf, h_rect)

    # Calcul des jours à afficher
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=29)
    start_monday = start_date - datetime.timedelta(days=start_date.weekday())
    end_sunday = today + datetime.timedelta(days=6 - today.weekday())

    curr = start_monday
    while curr <= end_sunday:
        col = curr.weekday()
        row = (curr - start_monday).days // 7
        x = CALENDAR_X + col * CELL_SIZE
        y = GRID_START_Y + row * CELL_SIZE
        rect = pygame.Rect(x, y, CELL_GAP, CELL_GAP)

        is_in_range = start_date <= curr <= today

        if is_in_range:
            is_selected = selected_date == curr
            is_today = curr == today

            # Déterminer la couleur du fond du jour
            if is_selected:
                bg_color = pygame.Color("#81b64c")
                text_color = pygame.Color("#ffffff")
            elif is_today:
                bg_color = pygame.Color("#403e3a")
                text_color = pygame.Color("#ffffff")
            else:
                bg_color = pygame.Color("#312e2b")
                text_color = pygame.Color("#c3c2c1")

            border_rad = max(1, int(3 * scale))
            pygame.draw.rect(screen, bg_color, rect, border_radius=border_rad)

            if is_today and not is_selected:
                # Dessiner une bordure subtile pour aujourd'hui
                pygame.draw.rect(
                    screen, pygame.Color("#81b64c"), rect, width=max(1, int(1 * scale)), border_radius=border_rad
                )

            # Dessiner le numéro du jour
            day_num_str = str(curr.day)
            day_surf = cal_day_font.render(day_num_str, True, text_color)
            screen.blit(day_surf, day_surf.get_rect(center=rect.center))

            # S'il y a des parties ce jour-là, on dessine une pastille verte
            if games_per_day and games_per_day.get(curr, 0) > 0:
                dot_color = (
                    pygame.Color("#ffffff") if is_selected else pygame.Color("#81b64c")
                )
                dot_y = rect.bottom - max(1, int(3 * scale))
                dot_r = max(1, int(2 * scale))
                pygame.draw.circle(
                    screen, dot_color, (rect.centerx, dot_y), dot_r
                )
        else:
            # Hors de la plage des 30 jours (jours de remplissage de la semaine)
            day_num_str = str(curr.day)
            day_surf = cal_day_font.render(day_num_str, True, pygame.Color("#403e3a"))
            screen.blit(day_surf, day_surf.get_rect(center=rect.center))

        curr += datetime.timedelta(days=1)

    # --- STATS DE L'UTILISATEUR ---
    stats_font = pygame.font.SysFont("Arial", int(12 * scale))
    stats_title_font = pygame.font.SysFont("Arial", int(13 * scale), bold=True)

    stats_title_surf = stats_title_font.render(
        "MES STATS", True, pygame.Color("#ffffff")
    )
    screen.blit(stats_title_surf, (BOARD_WIDTH + int(20 * scale), int(310 * scale)))

    if win_stats:
        stat_box_size = int(10 * scale)
        # Total
        pygame.draw.rect(
            screen, pygame.Color("#81b64c"), pygame.Rect(BOARD_WIDTH + int(20 * scale), int(332 * scale), stat_box_size, stat_box_size)
        )
        pygame.draw.rect(
            screen,
            pygame.Color("#7d7c7a"),
            pygame.Rect(BOARD_WIDTH + int(20 * scale), int(332 * scale), stat_box_size, stat_box_size),
            width=max(1, int(1 * scale)),
        )
        total_text = f"Total : {win_stats['total_games']} parties ({win_stats['total_win_pct']:.1f}% gains)"
        total_surf = stats_font.render(total_text, True, pygame.Color("#c3c2c1"))
        screen.blit(total_surf, (BOARD_WIDTH + int(38 * scale), int(330 * scale)))

        # Blancs
        pygame.draw.rect(
            screen, pygame.Color("#ffffff"), pygame.Rect(BOARD_WIDTH + int(20 * scale), int(350 * scale), stat_box_size, stat_box_size)
        )
        pygame.draw.rect(
            screen,
            pygame.Color("#7d7c7a"),
            pygame.Rect(BOARD_WIDTH + int(20 * scale), int(350 * scale), stat_box_size, stat_box_size),
            width=max(1, int(1 * scale)),
        )
        white_text = f"Blancs : {win_stats['white_games']} parties ({win_stats['white_win_pct']:.1f}% gains)"
        white_surf = stats_font.render(white_text, True, pygame.Color("#c3c2c1"))
        screen.blit(white_surf, (BOARD_WIDTH + int(38 * scale), int(348 * scale)))

        # Noirs
        pygame.draw.rect(
            screen, pygame.Color("#312e2b"), pygame.Rect(BOARD_WIDTH + int(20 * scale), int(368 * scale), stat_box_size, stat_box_size)
        )
        pygame.draw.rect(
            screen,
            pygame.Color("#7d7c7a"),
            pygame.Rect(BOARD_WIDTH + int(20 * scale), int(368 * scale), stat_box_size, stat_box_size),
            width=max(1, int(1 * scale)),
        )
        black_text = f"Noirs : {win_stats['black_games']} parties ({win_stats['black_win_pct']:.1f}% gains)"
        black_surf = stats_font.render(black_text, True, pygame.Color("#c3c2c1"))
        screen.blit(black_surf, (BOARD_WIDTH + int(38 * scale), int(366 * scale)))

    # --- AFFICHAGE DES STATS ---
    y_offset = int(413 * scale)

    # Titre des stats
    stats_title_text = "STATS OPPOSE"
    if selected_date:
        stats_title_text += f" ({selected_date.strftime('%d/%m')})"
    elif selected_days:
        stats_title_text += f" ({selected_days} J)"

    stats_title = title_font.render(stats_title_text, True, pygame.Color("#ffffff"))
    screen.blit(stats_title, (BOARD_WIDTH + int(20 * scale), y_offset - int(25 * scale)))

    if not stats:
        no_data = pygame.font.SysFont("Arial", int(15 * scale)).render(
            "Aucune partie trouvée", True, pygame.Color("#989795")
        )
        screen.blit(no_data, (BOARD_WIDTH + int(20 * scale), y_offset))
    else:
        for i, (move_french_san, count, pct) in enumerate(stats):
            if (
                i >= 5
            ):  # Max 5 stats pour éviter de déborder avec les nouvelles stats utilisateur
                break
            stat_text = f"{i+1}.  {move_french_san}"
            value_text = f"{count}x  ({pct:.1f}%)"

            move_surf = text_font.render(stat_text, True, pygame.Color("#ffffff"))
            val_surf = text_font.render(
                value_text,
                True,
                pygame.Color("#81b64c") if i == 0 else pygame.Color("#989795"),
            )

            screen.blit(move_surf, (BOARD_WIDTH + int(20 * scale), y_offset))
            screen.blit(val_surf, (BOARD_WIDTH + int(140 * scale), y_offset))
            y_offset += int(28 * scale)

    help_font = pygame.font.SysFont("Arial", int(13 * scale), italic=True)
    help_surf = help_font.render(
        "Navigation : Flèches ◄  ►", True, pygame.Color("#7d7c7a")
    )
    screen.blit(help_surf, (BOARD_WIDTH + int(45 * scale), BOARD_HEIGHT - int(30 * scale)))


# --- APPLICATION PRINCIPALE ---
def main():
    global BOARD_WIDTH, BOARD_HEIGHT, SQ_SIZE, SIDE_PANEL_WIDTH, WIDTH, HEIGHT
    global BTN_1J, BTN_7J, BTN_30J, BTN_FLIP

    print(f"Téléchargement de la base de données pour {USERNAME}...")
    all_loaded_games = get_recent_games(USERNAME, days=30)
    print(f"{len(all_loaded_games)} parties chargées.")

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Coach Échecs - Multi-perspectives")

    board_img, pieces_images = load_assets()
    board = chess.Board()

    selected_square = None
    dragged_pos = None
    selected_days = 7
    selected_date = None
    board_flipped = False

    all_moves = []
    move_index = 0

    # Dictionnaire de parties par jour pour l'affichage des pastilles vertes dans le calendrier
    games_per_day = {}
    for g in all_loaded_games:
        end_time = g.get("end_time", 0)
        if end_time:
            g_date = datetime.date.fromtimestamp(end_time)
            games_per_day[g_date] = games_per_day.get(g_date, 0) + 1

    filtered_games = filter_games(
        all_loaded_games, days=selected_days, target_date=selected_date
    )
    win_stats = get_game_win_stats(filtered_games, USERNAME)
    current_stats = get_opponent_move_stats(filtered_games, board.fen())

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                new_w, new_h = event.size

                scale_w = new_w / 850.0
                scale_h = new_h / 600.0
                scale = max(scale_w, scale_h)
                scale = max(scale, 1.0)

                board_size = int(600 * scale)
                board_size = (board_size // 8) * 8

                BOARD_WIDTH = board_size
                BOARD_HEIGHT = board_size
                SQ_SIZE = BOARD_WIDTH // 8
                SIDE_PANEL_WIDTH = BOARD_WIDTH * 250 // 600

                WIDTH = BOARD_WIDTH + SIDE_PANEL_WIDTH
                HEIGHT = BOARD_HEIGHT

                screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                board_img, pieces_images = load_assets()

                BTN_1J = pygame.Rect(BOARD_WIDTH + int(15 * scale), int(55 * scale), int(65 * scale), int(30 * scale))
                BTN_7J = pygame.Rect(BOARD_WIDTH + int(90 * scale), int(55 * scale), int(65 * scale), int(30 * scale))
                BTN_30J = pygame.Rect(BOARD_WIDTH + int(165 * scale), int(55 * scale), int(65 * scale), int(30 * scale))
                BTN_FLIP = pygame.Rect(BOARD_WIDTH + int(15 * scale), int(95 * scale), int(215 * scale), int(30 * scale))

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and move_index > 0:
                    move_index -= 1
                    board = chess.Board()
                    for m in all_moves[:move_index]:
                        board.push(m)
                    current_stats = get_opponent_move_stats(filtered_games, board.fen())

                elif event.key == pygame.K_RIGHT and move_index < len(all_moves):
                    move_index += 1
                    board = chess.Board()
                    for m in all_moves[:move_index]:
                        board.push(m)
                    current_stats = get_opponent_move_stats(filtered_games, board.fen())

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                if pos[0] < BOARD_WIDTH:
                    col = pos[0] // SQ_SIZE
                    row = pos[1] // SQ_SIZE

                    file = 7 - col if board_flipped else col
                    rank = row if board_flipped else 7 - row

                    square = chess.square(file, rank)
                    if board.piece_at(square):
                        selected_square = square
                else:
                    if BTN_FLIP.collidepoint(pos):
                        board_flipped = not board_flipped
                    else:
                        changed = False
                        if BTN_1J.collidepoint(pos) and selected_days != 1:
                            selected_days = 1
                            selected_date = None
                            changed = True
                        elif BTN_7J.collidepoint(pos) and selected_days != 7:
                            selected_days = 7
                            selected_date = None
                            changed = True
                        elif BTN_30J.collidepoint(pos) and selected_days != 30:
                            selected_days = 30
                            selected_date = None
                            changed = True
                        else:
                            # Clic sur le calendrier
                            today = datetime.date.today()
                            start_date = today - datetime.timedelta(days=29)
                            start_monday = start_date - datetime.timedelta(
                                days=start_date.weekday()
                            )
                            end_sunday = today + datetime.timedelta(
                                days=6 - today.weekday()
                            )

                            scale = BOARD_WIDTH / 600.0
                            CALENDAR_X = BOARD_WIDTH + int(48 * scale)
                            GRID_START_Y = int(168 * scale)
                            CELL_SIZE = int(22 * scale)
                            CELL_GAP = int(20 * scale)

                            curr = start_monday
                            while curr <= end_sunday:
                                col = curr.weekday()
                                row = (curr - start_monday).days // 7
                                x = CALENDAR_X + col * CELL_SIZE
                                y = GRID_START_Y + row * CELL_SIZE
                                rect = pygame.Rect(x, y, CELL_GAP, CELL_GAP)

                                if (
                                    rect.collidepoint(pos)
                                    and start_date <= curr <= today
                                ):
                                    if selected_date == curr:
                                        selected_date = None
                                        selected_days = (
                                            7  # Par défaut, revient à 7 jours
                                        )
                                    else:
                                        selected_date = curr
                                        selected_days = None
                                    changed = True
                                    break
                                curr += datetime.timedelta(days=1)

                        if changed:
                            filtered_games = filter_games(
                                all_loaded_games,
                                days=selected_days,
                                target_date=selected_date,
                            )
                            win_stats = get_game_win_stats(filtered_games, USERNAME)
                            current_stats = get_opponent_move_stats(
                                filtered_games, board.fen()
                            )

            # Correction des conditions de mouvement (is not None) pour éviter le blocage
            elif event.type == pygame.MOUSEMOTION and selected_square is not None:
                dragged_pos = pygame.mouse.get_pos()

            elif event.type == pygame.MOUSEBUTTONUP and selected_square is not None:
                pos = pygame.mouse.get_pos()
                if pos[0] < BOARD_WIDTH:
                    col = pos[0] // SQ_SIZE
                    row = pos[1] // SQ_SIZE

                    file = 7 - col if board_flipped else col
                    rank = row if board_flipped else 7 - row
                    target_square = chess.square(file, rank)

                    move = chess.Move(selected_square, target_square)
                    if (
                        board.piece_at(selected_square)
                        and board.piece_at(selected_square).piece_type == chess.PAWN
                        and chess.square_rank(target_square) in [0, 7]
                    ):
                        move.promotion = chess.QUEEN

                    if move in board.legal_moves:
                        if move_index < len(all_moves):
                            all_moves = all_moves[:move_index]

                        all_moves.append(move)
                        board.push(move)
                        move_index += 1
                        current_stats = get_opponent_move_stats(
                            filtered_games, board.fen()
                        )

                selected_square = None
                dragged_pos = None

        # Rendu graphique
        draw_board(screen, board_img, board_flipped)
        draw_pieces(
            screen, board, pieces_images, board_flipped, selected_square, dragged_pos
        )
        draw_side_panel(
            screen,
            current_stats,
            selected_days,
            selected_date,
            games_per_day,
            win_stats,
        )

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
