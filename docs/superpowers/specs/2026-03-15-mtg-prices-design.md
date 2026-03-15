# MTG Prices — Design Spec

## Overview

Outil CLI Python pour suivre les prix des cartes Magic: The Gathering via l'API Scryfall. L'utilisateur fournit un fichier texte (decklist), le script scrape les prix quotidiennement et affiche les tendances sur 7 et 30 jours.

## Input

Fichier texte, une carte par ligne au format `<quantité> <nom de la carte>` :

```
1 Sheoldred, the Apocalypse
4 Lightning Bolt
1 Demonic Tutor
23 Swamp
```

- Quantité (entier) + espace + nom exact (anglais, tel que sur Scryfall)
- Lignes vides ignorées
- Lignes commençant par `#` ignorées (commentaires)
- Lignes mal formées : warning + skip

## Source de prix

**Scryfall API** (gratuite, sans clé).

### Stratégie de sélection

Pour chaque carte :

1. Appel `/cards/search?q=!"{name}"&order=released&dir=desc` — le query doit être URL-encodé (noms avec virgules, apostrophes, etc.)
2. Parcours des 5 éditions les plus récentes (la première page de résultats suffit grâce au tri)
3. Sélection du prix non-foil (`prices.usd` / `prices.eur`) le plus bas — les prix foil sont ignorés
4. Les cartes avec `prices.usd: null` sont skippées dans la sélection (pas de prix disponible)
5. Fallback sur `/cards/named?fuzzy={name}` si la recherche exacte échoue
6. Cartes à double face (MDFC, split, transform) : on utilise le nom de la face avant uniquement. Scryfall résout correctement `!"Delver of Secrets"` vers la carte complète.

Les prix Scryfall sont des strings (`"72.50"`) — conversion en `float` à l'insertion.

### Headers HTTP requis

Toutes les requêtes doivent inclure :
- `User-Agent: mtg-prices/1.0` (identifiant de l'application, exigé par Scryfall)
- `Accept: application/json`

### Rate limiting

- 100ms entre chaque requête (fourchette haute de la recommandation Scryfall 50-100ms, choix prudent)
- Retry avec backoff exponentiel (3 tentatives max) en cas d'erreur 429/5xx

### Fréquence

- Scryfall met à jour ses prix une fois par jour
- Le fetch est prévu via crontab externe, quelques minutes après le refresh Scryfall

## Storage

### SQLite

Fichier unique dans `data/mtg_prices.db`.

```sql
CREATE TABLE cards (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    scryfall_id TEXT
);

CREATE TABLE prices (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    price_usd REAL,
    price_eur REAL,
    set_code TEXT NOT NULL,
    set_name TEXT NOT NULL,
    fetched_at DATE NOT NULL,
    UNIQUE(card_id, fetched_at)
);

CREATE INDEX idx_prices_card_date ON prices(card_id, fetched_at);
```

- Une entrée par carte par jour (`UNIQUE(card_id, fetched_at)`)
- Upsert via `INSERT ... ON CONFLICT(card_id, fetched_at) DO UPDATE SET ...` si on relance le fetch le même jour (préserve l'id de la ligne)
- USD et EUR stockés

## CLI

Package installable via `pip install -e .` avec entrypoint `mtg-prices`.

### Commandes

```bash
# Scrape les prix et stocke en DB
mtg-prices fetch cards.txt

# Affiche les tendances + export optionnel
mtg-prices report cards.txt
mtg-prices report cards.txt --format csv
mtg-prices report cards.txt --format json --output prices.json
```

### Options du report

| Option       | Description                              | Défaut                          |
|-------------|------------------------------------------|---------------------------------|
| `--format`  | Format d'export (`csv`, `json`)          | Console uniquement              |
| `--output`  | Chemin du fichier d'export               | `data/export_{date}.{format}`   |
| `--currency`| Devise (`usd`, `eur`)                   | `usd`                           |

## Output

### Console (Rich)

```
┌─────┬─────────────────────────────────┬──────────┬──────┬──────────┬───────┐
│ Qté │ Carte                           │ Prix     │ Ext  │ 7j       │ 30j   │
├─────┼─────────────────────────────────┼──────────┼──────┼──────────┼───────┤
│ 1   │ Sheoldred, the Apocalypse       │ $72.50   │ ONE  │ +3.2%    │ -1.8% │
│ 1   │ Demonic Tutor                   │ $35.20   │ DMR  │ +0.5%    │ +2.1% │
│ 1   │ Vampiric Tutor                  │ $28.00   │ CMM  │ -1.0%    │ -4.3% │
├─────┼─────────────────────────────────┼──────────┼──────┼──────────┼───────┤
│ 73  │ TOTAL                           │ $385.40  │      │ +1.2%    │ -0.5% │
└─────┴─────────────────────────────────┴──────────┴──────┴──────────┴───────┘
```

- Tendances colorées : vert (hausse), rouge (baisse)
- Historique insuffisant (< 7j ou < 30j) : affiche `—`
- Trié par prix décroissant
- Extension en code court (ONE, DMR, CMM, etc.)

### Export CSV

```csv
qty,name,price_usd,price_eur,set_code,trend_7d,trend_30d
1,"Sheoldred, the Apocalypse",72.50,65.00,ONE,+3.2%,-1.8%
```

Les noms contenant des virgules sont quotés (RFC 4180).

### Export JSON

```json
[
  {
    "qty": 1,
    "name": "Sheoldred, the Apocalypse",
    "price_usd": 72.50,
    "price_eur": 65.00,
    "set_code": "ONE",
    "trend_7d": 3.2,
    "trend_30d": -1.8
  }
]
```

## Architecture

```
mtg-prices/
├── pyproject.toml
├── src/
│   └── mtg_prices/
│       ├── __init__.py
│       ├── cli.py          # Point d'entrée Click
│       ├── scraper.py      # Client Scryfall API
│       ├── db.py           # Couche SQLite
│       ├── report.py       # Formatage console + export
│       └── models.py       # Dataclasses
├── tests/
│   ├── conftest.py
│   ├── test_scraper.py
│   ├── test_db.py
│   └── test_report.py
└── data/                   # DB SQLite + exports (gitignored)
```

### Dépendances

| Package | Usage                    |
|---------|--------------------------|
| click   | CLI framework            |
| httpx   | Client HTTP              |
| rich    | Tableaux formatés        |
| pytest  | Tests                    |

### Modules

- **cli.py** — Parsing des arguments, orchestration des commandes `fetch` et `report`
- **scraper.py** — Client Scryfall : recherche de cartes, récupération des prix, gestion du rate limit
- **db.py** — Init DB, insertion des prix, requêtes de tendance (prix à J-7, J-30)
- **report.py** — Construction du tableau Rich, export CSV/JSON
- **models.py** — Dataclasses `Card`, `PriceEntry`, `CardReport`

## Calcul des tendances

Formule : `(prix_aujourd'hui - prix_J-N) / prix_J-N * 100`

- **7j** : prix du jour vs prix il y a 7 jours
- **30j** : prix du jour vs prix il y a 30 jours
- Si le prix exact à J-N est absent, on prend le prix le plus proche disponible dans une fenêtre de ±2 jours
- Si aucun prix n'est disponible dans la fenêtre : affiche `—`

## Logging

Logging via le module `logging` de Python :
- Console : `WARNING` et au-dessus
- Fichier `data/errors.log` : `INFO` et au-dessus (rotation quotidienne)

## Gestion des erreurs

| Situation                    | Comportement                                              |
|-----------------------------|-----------------------------------------------------------|
| Carte introuvable           | Warning console, skip, log dans `data/errors.log`         |
| Scryfall indisponible / 429 | Retry backoff exponentiel (3 max), puis abandon + message |
| DB inaccessible             | Message d'erreur explicite, exit code non-zéro            |
| Ligne mal formée            | Warning + skip, continue le reste                         |
| Pas d'historique suffisant  | Affiche `—` pour les tendances manquantes                 |
| Prix null sur Scryfall      | Skip dans la sélection, warning si aucun prix disponible  |
