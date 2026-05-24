# Chess Coach

## Présentation

`chess-coach` est une application Python de visualisation et d’analyse d’échecs qui exploite l’API publique de Chess.com. Elle permet de charger vos parties récentes, d’avancer coup par coup sur un plateau interactif et de voir quelles réponses d’adversaires sont les plus fréquentes à une position donnée.

L’interface utilise `pygame` pour dessiner le plateau et afficher les statistiques de coups en français (notation algébrique standard adaptée au français).

## Fonctionnalités

- Chargement des parties récentes depuis Chess.com
- Filtrage des parties par période : 1 jour, 7 jours, 30 jours
- Plateau interactif avec glisser-déposer des pièces
- Navigation dans la séquence de coups avec les flèches gauche/droite
- Affichage des coups les plus probables joués par l’adversaire dans une position donnée
- Support des images de plateau et de pièces si les fichiers existent dans `images/`

## Prérequis

- Python 3.10 ou supérieur
- `pygame`
- `python-chess`
- `requests`

## Installation

1. Clonez le dépôt :

```bash
git clone https://github.com/votre-utilisateur/chess-coach.git
cd chess-coach
```

2. Créez et activez un environnement Python :

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

3. Installez les dépendances :

```bash
pip install -r requirements.txt
```

## Configuration

Copiez ou renommez `config.json.example` en `config.json` puis éditez les valeurs :

```json
{
    "username": "PseudoChessCom",
    "email": "ton_email@example.com"
}
```

- `username` : votre pseudo Chess.com
- `email` : adresse de contact utilisée dans l’en-tête `User-Agent`

Si `config.json` est absent, l’application se lance avec des valeurs par défaut (`PseudoParDefaut` et `contact@example.com`).

## Utilisation

Lancez l’application avec :

```bash
python app.py
```

### Contrôles

- Cliquez sur une pièce pour la sélectionner
- Déplacez-la à l’endroit voulu et relâchez
- Flèche gauche ◄ : reculer d’un coup
- Flèche droite ► : avancer d’un coup
- Bouton `Tourner l'échiquier` : inverse la vue du plateau
- Boutons `1 J`, `7 J`, `30 J` : filtrer les parties récentes

### Panneau latéral

Le panneau à droite affiche :

- les coups les plus joués par l’adversaire depuis la position actuelle
- le nombre d’occurrences et le pourcentage de chaque coup

## Structure du dépôt

- `app.py` : application principale
- `config.json.example` : exemple de configuration
- `images/boards/` : images possibles pour le plateau
- `images/pieces/` : images possibles pour les pièces

## Contributions

Les contributions sont les bienvenues. Ouvrez une issue ou une pull request pour proposer des améliorations, corriger des bugs ou ajouter des fonctionnalités.

## Licence

Ce projet peut être utilisé librement. Ajoutez votre licence préférée si nécessaire.
