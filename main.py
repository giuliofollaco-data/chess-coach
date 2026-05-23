import datetime
import sys
import chess
import pygame
import requests

# --- CONFIGURATION & API CHESS.COM ---
USERNAME = "giugiugiulio"  # Remplace par ton pseudo Chess.com
HEADERS = {"User-Agent": "ChessCoachApp/1.0 (contact: giuliofollaco@gmail.com)"}

# Dimensions de la fenêtre de jeu
WIDTH, HEIGHT = 600, 600
SQ_SIZE = WIDTH // 8
COLORS = [pygame.Color("#eeeed2"), pygame.Color("#769656")]

# Dictionnaire de correspondance entre les pièces de la bibliothèque 'chess' et tes fichiers d'images
PIECE_TO_NAME = {
    "P": "wp",
    "R": "wr",
    "N": "wn",
    "B": "wb",
    "Q": "wq",
    "K": "wk",  # Pièces blanches (White)
    "p": "bp",
    "r": "br",
    "n": "bn",
    "b": "bb",
    "q": "bq",
    "k": "bk",  # Pièces noires (Black)
}


# --- CHARGEMENT DES PARTIES ---
def get_games_for_month(username, year, month):
    url = f"https://api.chess.com/pub/player/{username}/games/{year}/{month:02d}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get("games", [])
    return []


def get_recent_games(username, days=7):
    now = datetime.datetime.now()
    all_games = []

    months_to_check = {now.month: now.year}
    if now.day < days:
        prev = now - datetime.timedelta(days=days)
        months_to_check[prev.month] = prev.year

    for m, y in months_to_check.items():
        all_games.extend(get_games_for_month(username, y, m))

    cutoff_timestamp = (now - datetime.timedelta(days=days)).timestamp()
    recent_games = []

    for game in all_games:
        end_time = game.get("end_time", 0)
        if end_time >= cutoff_timestamp:
            recent_games.append(game)

    return recent_games


# --- ANALYSE DES COUPS DES ADVERSAIRES ---
def get_opponent_move_stats(games, current_fen):
    board_target = chess.Board(current_fen)
    target_key = " ".join(board_target.fen().split()[:4])

    move_counts = {}
    total_matches = 0

    for game in games:
        if "pgn" not in game:
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
                    move_uci = move.uci()
                    move_counts[move_uci] = move_counts.get(move_uci, 0) + 1
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


# --- RECHERCHE ET RECONNAISSANCE DES IMAGES (FALLBACKS INCLUS) ---
def load_assets():
    """Charge les textures de l'échiquier et des pièces de manière sécurisée"""
    board_img = None
    pieces_images = {}

    # 1. Tentative de chargement du plateau personnalisé
    try:
        board_img = pygame.image.load("./images/boards/green.png")
        board_img = pygame.transform.scale(board_img, (WIDTH, HEIGHT))
        print("✓ Texture du plateau './images/boards/green.png' chargée avec succès.")
    except (pygame.error, FileNotFoundError):
        print(
            "⚠ Impossible de charger './images/boards/green.png'. Utilisation de l'échiquier par défaut."
        )

    # 2. Tentative de chargement des pièces personnalisées
    for symbol, name in PIECE_TO_NAME.items():
        path = f"./images/pieces/{name}.png"
        try:
            img = pygame.image.load(path)
            img = pygame.transform.scale(img, (SQ_SIZE, SQ_SIZE))
            pieces_images[symbol] = img
        except (pygame.error, FileNotFoundError):
            print(f"⚠ Pièce manquante : '{path}'. Elle s'affichera en texte unicode.")
            pieces_images[symbol] = None

    return board_img, pieces_images


# --- DESSIN DU JEU ---
def draw_board(screen, board_img):
    """Affiche l'échiquier texturé ou dessine la grille par défaut si manquant"""
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
    """Affiche les pièces sous forme d'image ou de texte unicode de secours"""
    # Caractères unicode de secours
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

            # Ne pas afficher sur sa case d'origine si la pièce est déplacée à la souris
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

    # Dessiner la pièce tenue au curseur
    if dragged_piece and dragged_pos:
        piece = board.piece_at(dragged_piece)
        symbol = piece.symbol()
        img = pieces_images.get(symbol)
        if img:
            # Centre l'image de la pièce sur le curseur de la souris
            screen.blit(
                img, (dragged_pos[0] - SQ_SIZE // 2, dragged_pos[1] - SQ_SIZE // 2)
            )
        else:
            text_surface = font.render(fallback_symbols[symbol], True, (0, 0, 0))
            screen.blit(text_surface, (dragged_pos[0] - 20, dragged_pos[1] - 30))


# --- PROGRAMME PRINCIPAL ---
def main():
    print(f"Téléchargement des parties récentes pour {USERNAME}...")
    recent_games = get_recent_games(USERNAME, days=7)
    print(f"{len(recent_games)} parties chargées.")

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Coach Échecs Visuel")

    # Chargement des textures externes
    board_img, pieces_images = load_assets()

    board = chess.Board()
    selected_square = None
    dragged_pos = None

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                col = pos[0] // SQ_SIZE
                row = 7 - (pos[1] // SQ_SIZE)
                square = chess.square(col, row)

                if board.piece_at(square):
                    selected_square = square

            elif event.type == pygame.MOUSEMOTION and selected_square:
                dragged_pos = pygame.mouse.get_pos()

            elif event.type == pygame.MOUSEBUTTONUP and selected_square:
                pos = pygame.mouse.get_pos()
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
                    board.push(move)
                    print(
                        f"\nNouveau coup joué. Position actuelle (FEN): {board.fen()}"
                    )

                    # Recherche des statistiques adverses
                    stats = get_opponent_move_stats(recent_games, board.fen())
                    if stats:
                        print("Statistiques des adversaires pour cette position :")
                        for move_uci, count, pct in stats:
                            print(
                                f"  Coup : {move_uci} | Joué {count} fois ({pct:.1f}%)"
                            )
                    else:
                        print(
                            "Aucune statistique dans votre historique pour cette position."
                        )

                selected_square = None
                dragged_pos = None

        draw_board(screen, board_img)
        draw_pieces(screen, board, pieces_images, selected_square, dragged_pos)
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
