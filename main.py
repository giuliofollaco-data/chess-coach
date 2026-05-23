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

COLORS = [
    pygame.Color("#eeeed2"),
    pygame.Color("#769656"),
]  # [Cases Claire, Cases Sombres]
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


# --- FILTRE LOCAL & STATS ---
def filter_games_by_days(games, days):
    now = datetime.datetime.now()
    cutoff_timestamp = (now - datetime.timedelta(days=days)).timestamp()
    return [g for g in games if g.get("end_time", 0) >= cutoff_timestamp]


def get_opponent_move_stats(games, current_fen):
    board_target = chess.Board(current_fen)
    target_key = " ".join(board_target.fen().split()[:4])
    target_turn = board_target.turn

    move_counts = {}
    total_matches = 0

    for game in games:
        if "pgn" not in game:
            continue

        # Filtre exclusif pour n'avoir que les coups de tes adversaires
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


def draw_board(screen, board_img, board_flipped):
    """Dessine l'échiquier en gérant la rotation à 180°"""
    if board_img:
        if board_flipped:
            # Effectue une rotation de l'image de texture si l'échiquier est retourné
            screen.blit(pygame.transform.rotate(board_img, 180), (0, 0))
        else:
            screen.blit(board_img, (0, 0))
    else:
        # Fallback de dessin manuel si l'image est absente
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
    """Affiche les pièces sur l'échiquier selon le sens de lecture choisi"""
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
            row = chess.square_rank(square)

            # Inversion mathématique des coordonnées si board_flipped est actif
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
                screen.blit(text_surface, (x + 15, y + 5))

    # Dessin de la pièce tenue au curseur
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
# Nouveau bouton pour pivoter l'échiquier
BTN_FLIP = pygame.Rect(BOARD_WIDTH + 15, 95, 215, 30)


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

    title_surface = title_font.render("COACH - OPTIONS", True, pygame.Color("#ffffff"))
    screen.blit(title_surface, (BOARD_WIDTH + 20, 20))

    # Dessin filtres temporels
    buttons = [(BTN_1J, "1 J", 1), (BTN_7J, "7 J", 7), (BTN_30J, "30 J", 30)]
    for rect, label, days in buttons:
        is_active = selected_days == days
        bg_color = pygame.Color("#81b64c") if is_active else pygame.Color("#312e2b")
        text_color = pygame.Color("#ffffff") if is_active else pygame.Color("#989795")
        pygame.draw.rect(screen, bg_color, rect, border_radius=4)
        btn_text = btn_font.render(label, True, text_color)
        screen.blit(btn_text, btn_text.get_rect(center=rect.center))

    # Dessin du bouton Flip Board
    pygame.draw.rect(screen, pygame.Color("#312e2b"), BTN_FLIP, border_radius=4)
    flip_text = btn_font.render("Tourner l'échiquier", True, pygame.Color("#ffffff"))
    screen.blit(flip_text, flip_text.get_rect(center=BTN_FLIP.center))

    # Statistiques des coups (décalées à y=150 pour laisser de la place)
    y_offset = 150
    if not stats:
        no_data = pygame.font.SysFont("Arial", 15).render(
            "Aucune partie trouvée", True, pygame.Color("#989795")
        )
        screen.blit(no_data, (BOARD_WIDTH + 20, y_offset))
    else:
        for i, (move_french_san, count, pct) in enumerate(stats):
            if i >= 9:  # Sécurité hauteur max pour l'aide en bas
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
    pygame.display.set_caption("Coach Échecs - Option Pivot Échiquier")

    board_img, pieces_images = load_assets()
    board = chess.Board()

    selected_square = None
    dragged_pos = None
    selected_days = 7
    board_flipped = False  # Par défaut, les blancs sont en bas

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
                    # CLIC SUR L'ÉCHIQUIER (Prise en compte de l'inversion)
                    col = pos[0] // SQ_SIZE
                    row = pos[1] // SQ_SIZE

                    file = 7 - col if board_flipped else col
                    rank = row if board_flipped else 7 - row

                    square = chess.square(file, rank)
                    if board.piece_at(square):
                        selected_square = square
                else:
                    # CLIC SUR LE PANNEAU LATÉRAL
                    if BTN_FLIP.collidepoint(pos):
                        board_flipped = not board_flipped
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
                    row = pos[1] // SQ_SIZE

                    file = 7 - col if board_flipped else col
                    rank = row if board_flipped else 7 - rank
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
        draw_side_panel(screen, current_stats, selected_days)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
