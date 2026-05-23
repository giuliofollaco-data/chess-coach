import datetime
import sys
import chess
import pygame
import requests

# --- CONFIGURATION & API CHESS.COM ---
USERNAME = "giugiugiulio"
HEADERS = {"User-Agent": "ChessCoachApp/1.0 (contact: giuliofollaco@gmail.com)"}

# Dimensions de la fenêtre
BOARD_WIDTH, BOARD_HEIGHT = 600, 600
SIDE_PANEL_WIDTH = 250
WIDTH = BOARD_WIDTH + SIDE_PANEL_WIDTH
HEIGHT = BOARD_HEIGHT
SQ_SIZE = BOARD_WIDTH // 8

COLORS = [pygame.Color("#eeeed2"), pygame.Color("#769656")]
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
    """Traduit la notation algébrique anglaise (Nf3, Bxe4) en notation officielle française (Cf3, Fxe4)"""
    mapping = {
        "K": "R",  # King -> Roi
        "Q": "D",  # Queen -> Dame
        "R": "T",  # Rook -> Tour
        "B": "F",  # Bishop -> Fou
        "N": "C",  # Knight -> Cavalier
    }
    # On ne traduit que les lettres majuscules (les pièces), les minuscules restent les cases (a-h)
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


# --- FILTRE LOCAL & STATS ---
def filter_games_by_days(games, days):
    now = datetime.datetime.now()
    cutoff_timestamp = (now - datetime.timedelta(days=days)).timestamp()
    return [g for g in games if g.get("end_time", 0) >= cutoff_timestamp]


def get_opponent_move_stats(games, current_fen):
    board_target = chess.Board(current_fen)
    target_key = " ".join(board_target.fen().split()[:4])

    # On détermine quelle couleur doit jouer dans la position actuelle étudiée
    # Si board_target.turn == chess.WHITE, on cherche le coup des Blancs.
    # Si board_target.turn == chess.BLACK, on cherche le coup des Noirs.
    target_turn = board_target.turn

    move_counts = {}
    total_matches = 0

    for game in games:
        if "pgn" not in game:
            continue

        # --- FILTRE ADVERSAIRE ---
        # On regarde la couleur de l'utilisateur "giugiugiulio" dans cette partie
        is_user_white = (
            game.get("white", {}).get("username", "").lower() == USERNAME.lower()
        )
        is_user_black = (
            game.get("black", {}).get("username", "").lower() == USERNAME.lower()
        )

        # Si le trait (le joueur qui doit jouer) correspond à notre propre couleur,
        # alors ce n'est pas un coup adverse ! On passe à la partie suivante.
        if target_turn == chess.WHITE and is_user_white:
            continue
        if target_turn == chess.BLACK and is_user_black:
            continue
        # -------------------------

        pgn_text = game["pgn"]
        board = chess.Board()

        moves = []
        for line in pgn_text.split("\n"):
            if line.startswith("[") or not line.strip():
                continue
            parts = line.split()
            for p in parts:
                if "." not in p and "{" not in p and "}" not in p:
                    moves.append(p)

        for move_san in moves:
            current_key = " ".join(board.fen().split()[:4])
            if current_key == target_key:
                try:
                    move = board.parse_san(move_san)
                    standard_san = board.san(move)
                    french_san = to_french_san(standard_san)

                    move_counts[french_san] = move_counts.get(french_san, 0) + 1
                    total_matches += 1
                    break
                except ValueError:
                    break
            try:
                board.push_san(move_san)
            except ValueError:
                break

    stats = []
    for m, count in move_counts.items():
        pct = (count / total_matches) * 100
        stats.append((m, count, pct))

    return sorted(stats, key=lambda x: x[1], reverse=True)


# --- GRAPHISMES & INTERFACE ---
def load_assets():
    board_img = None
    pieces_images = {}
    try:
        board_img = pygame.image.load("./images/boards/green.png")
        board_img = pygame.transform.scale(board_img, (BOARD_WIDTH, BOARD_HEIGHT))
    except (pygame.error, FileNotFoundError):
        pass

    for symbol, name in PIECE_TO_NAME.items():
        path = f"./images/pieces/{name}.png"
        try:
            img = pygame.image.load(path)
            img = pygame.transform.scale(img, (SQ_SIZE, SQ_SIZE))
            pieces_images[symbol] = img
        except (pygame.error, FileNotFoundError):
            pieces_images[symbol] = None
    return board_img, pieces_images


def draw_board(screen, board_img):
    if board_img:
        screen.blit(board_img, (0, 0))
    else:
        for r in range(8):
            for c in range(8):
                color = COLORS[((r + c) % 2)]
                pygame.draw.rect(
                    screen,
                    color,
                    pygame.Rect(c * SQ_SIZE, r * SQ_SIZE, SQ_SIZE, SQ_SIZE),
                )


def draw_pieces(screen, board, pieces_images, dragged_piece=None, dragged_pos=None):
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
    font = pygame.font.SysFont("Segoe UI Symbol", 50)

    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            symbol = piece.symbol()
            if dragged_piece and square == dragged_piece:
                continue

            col = chess.square_file(square)
            row = 7 - chess.square_rank(square)
            x, y = col * SQ_SIZE, row * SQ_SIZE

            img = pieces_images.get(symbol)
            if img:
                screen.blit(img, (x, y))
            else:
                text_surface = font.render(fallback_symbols[symbol], True, (0, 0, 0))
                screen.blit(text_surface, (x + 15, y + 5))

    if dragged_piece and dragged_pos:
        piece = board.piece_at(dragged_piece)
        symbol = piece.symbol()
        img = pieces_images.get(symbol)
        if img:
            screen.blit(
                img, (dragged_pos[0] - SQ_SIZE // 2, dragged_pos[1] - SQ_SIZE // 2)
            )
        else:
            text_surface = font.render(fallback_symbols[symbol], True, (0, 0, 0))
            screen.blit(text_surface, (dragged_pos[0] - 20, dragged_pos[1] - 30))


# --- PANNEAU LATÉRAL ---
BTN_1J = pygame.Rect(BOARD_WIDTH + 15, 55, 65, 30)
BTN_7J = pygame.Rect(BOARD_WIDTH + 90, 55, 65, 30)
BTN_30J = pygame.Rect(BOARD_WIDTH + 165, 55, 65, 30)


def draw_side_panel(screen, stats, selected_days):
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
        3,
    )

    title_font = pygame.font.SysFont("Arial", 16, bold=True)
    btn_font = pygame.font.SysFont("Arial", 14, bold=True)
    text_font = pygame.font.SysFont("Arial", 15, bold=True)

    title_surface = title_font.render("COACH - PÉRIODE", True, pygame.Color("#ffffff"))
    screen.blit(title_surface, (BOARD_WIDTH + 20, 20))

    buttons = [(BTN_1J, "1 J", 1), (BTN_7J, "7 J", 7), (BTN_30J, "30 J", 30)]
    for rect, label, days in buttons:
        is_active = selected_days == days
        bg_color = pygame.Color("#81b64c") if is_active else pygame.Color("#312e2b")
        text_color = pygame.Color("#ffffff") if is_active else pygame.Color("#989795")

        pygame.draw.rect(screen, bg_color, rect, border_radius=4)
        btn_text = btn_font.render(label, True, text_color)
        text_rect = btn_text.get_rect(center=rect.center)
        screen.blit(btn_text, text_rect)

    # Statistiques des coups (Affichage nettoyé en SAN français)
    y_offset = 120
    if not stats:
        no_data = pygame.font.SysFont("Arial", 15).render(
            "Aucune partie trouvée", True, pygame.Color("#989795")
        )
        screen.blit(no_data, (BOARD_WIDTH + 20, y_offset))
    else:
        for i, (move_french_san, count, pct) in enumerate(stats):
            if i >= 10:
                break
            stat_text = f"{i+1}.  {move_french_san}"
            value_text = f"{count}x  ({pct:.1f}%)"

            move_surf = text_font.render(stat_text, True, pygame.Color("#ffffff"))
            val_surf = text_font.render(
                value_text,
                True,
                pygame.Color("#81b64c") if i == 0 else pygame.Color("#989795"),
            )

            screen.blit(move_surf, (BOARD_WIDTH + 20, y_offset))
            screen.blit(val_surf, (BOARD_WIDTH + 140, y_offset))
            y_offset += 38

    help_font = pygame.font.SysFont("Arial", 13, italic=True)
    help_surf = help_font.render(
        "Navigation : Flèches ◄  ►", True, pygame.Color("#7d7c7a")
    )
    screen.blit(help_surf, (BOARD_WIDTH + 45, BOARD_HEIGHT - 35))


# --- APPLICATION PRINCIPALE ---
def main():
    print(f"Téléchargement de la base de données pour {USERNAME}...")
    all_loaded_games = get_recent_games(USERNAME, days=30)
    print(f"{len(all_loaded_games)} parties chargées.")

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Coach Échecs - Notation Officielle FR")

    board_img, pieces_images = load_assets()
    board = chess.Board()

    selected_square = None
    dragged_pos = None
    selected_days = 7

    all_moves = []
    move_index = 0

    filtered_games = filter_games_by_days(all_loaded_games, selected_days)
    current_stats = get_opponent_move_stats(filtered_games, board.fen())

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    if move_index > 0:
                        move_index -= 1
                        board = chess.Board()
                        for m in all_moves[:move_index]:
                            board.push(m)
                        current_stats = get_opponent_move_stats(
                            filtered_games, board.fen()
                        )

                elif event.key == pygame.K_RIGHT:
                    if move_index < len(all_moves):
                        move_index += 1
                        board = chess.Board()
                        for m in all_moves[:move_index]:
                            board.push(m)
                        current_stats = get_opponent_move_stats(
                            filtered_games, board.fen()
                        )

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                if pos[0] < BOARD_WIDTH:
                    col = pos[0] // SQ_SIZE
                    row = 7 - (pos[1] // SQ_SIZE)
                    square = chess.square(col, row)
                    if board.piece_at(square):
                        selected_square = square
                else:
                    changed = False
                    if BTN_1J.collidepoint(pos) and selected_days != 1:
                        selected_days = 1
                        changed = True
                    elif BTN_7J.collidepoint(pos) and selected_days != 7:
                        selected_days = 7
                        changed = True
                    elif BTN_30J.collidepoint(pos) and selected_days != 30:
                        selected_days = 30
                        changed = True

                    if changed:
                        filtered_games = filter_games_by_days(
                            all_loaded_games, selected_days
                        )
                        current_stats = get_opponent_move_stats(
                            filtered_games, board.fen()
                        )

            elif event.type == pygame.MOUSEMOTION and selected_square:
                dragged_pos = pygame.mouse.get_pos()

            elif event.type == pygame.MOUSEBUTTONUP and selected_square:
                pos = pygame.mouse.get_pos()
                if pos[0] < BOARD_WIDTH:
                    col = pos[0] // SQ_SIZE
                    row = 7 - (pos[1] // SQ_SIZE)
                    target_square = chess.square(col, row)

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
        draw_board(screen, board_img)
        draw_pieces(screen, board, pieces_images, selected_square, dragged_pos)
        draw_side_panel(screen, current_stats, selected_days)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
