# spotinew

Ajoute automatiquement, chaque jour, les **nouvelles sorties de tes artistes
suivis sur Spotify** dans une **playlist dédiée**, à partir d'une date donnée.

Tourne tout seul dans le cloud via **GitHub Actions** (gratuit, même PC éteint).

---

## Comment ça marche

À chaque exécution, le script :

1. récupère la liste de tes **artistes suivis** ;
2. détermine la **fenêtre de scan** : il repart de la date du **dernier titre
   ajouté** à la playlist (= dernier scan) ; au tout premier passage (playlist
   vide), il part de `START_DATE` ;
3. liste leurs **albums / singles** parus dans cette fenêtre ;
4. récupère les **pistes** et les **ajoute à la playlist** en évitant les doublons
   (comparaison au contenu actuel — **aucun fichier d'état à gérer**).

> ⏱️ **Reprise incrémentale.** Le repère « dernier scan » est lu directement
> depuis la playlist (date d'ajout la plus récente). Inutile de stocker un état
> ou de donner des droits d'écriture Git à GitHub Actions ; les doublons restent
> impossibles grâce à la comparaison avec la playlist.

> 💡 Spotify propose déjà une playlist auto « Release Radar », mais limitée à
> ~30 titres et non paramétrable. spotinew te donne le contrôle total
> (date de départ, playlist de ton choix, tout l'historique des nouveautés).

---

## Installation

### Étape 1 — Créer une application Spotify

1. Va sur le [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. **Create app**. Donne un nom (ex. `spotinew`), une description.
3. Dans **Redirect URIs**, ajoute exactement :
   ```
   http://127.0.0.1:8888/callback
   ```
   ⚠️ Spotify exige `127.0.0.1` (pas `localhost`).
4. Coche l'API **Web API**, enregistre.
5. Note le **Client ID** et le **Client Secret** (bouton *Settings*).

### Étape 2 — Obtenir un refresh token (en local, une seule fois)

```powershell
# Depuis le dossier du projet
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Configurer les identifiants
copy .env.example .env
# → édite .env et renseigne SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET

python src/auth_setup.py
```

Le script affiche une URL : ouvre-la, autorise l'app, puis **copie-colle l'URL
de redirection complète** (`http://127.0.0.1:8888/callback?code=...`).
La page peut afficher une erreur de connexion : **c'est normal**, seule l'URL compte.

Le script affiche alors ton **refresh token** : garde-le pour l'étape 4.

### Étape 3 — (Optionnel) Tester en local

Renseigne `SPOTIFY_REFRESH_TOKEN`, `START_DATE` et `SPOTIFY_PLAYLIST_NAME`
dans `.env`, puis :

```powershell
python src/sync.py
```

### Étape 4 — Automatiser avec GitHub Actions

1. Crée un dépôt GitHub et pousse ce projet.
2. Dans **Settings → Secrets and variables → Actions** :
   - Onglet **Secrets** → *New repository secret* :
     - `SPOTIFY_CLIENT_ID`
     - `SPOTIFY_CLIENT_SECRET`
     - `SPOTIFY_REFRESH_TOKEN`
   - Onglet **Variables** → *New repository variable* :
     - `START_DATE` → ex. `2026-01-01`
     - `SPOTIFY_PLAYLIST_NAME` → ex. `Nouveautés abonnements`
     - `SPOTIFY_PLAYLIST_ID` *(facultatif)* — pour cibler une playlist précise.
3. C'est tout. Le workflow tourne **chaque jour à 00:00 UTC (≈ 02:00 à Paris)**.
   Tu peux aussi le lancer à la main : onglet **Actions → spotinew → Run workflow**.

---

## Configuration

| Variable                | Type    | Rôle                                                            |
| ----------------------- | ------- | --------------------------------------------------------------- |
| `SPOTIFY_CLIENT_ID`     | secret  | Client ID de l'app Spotify                                      |
| `SPOTIFY_CLIENT_SECRET` | secret  | Client Secret de l'app Spotify                                  |
| `SPOTIFY_REFRESH_TOKEN` | secret  | Jeton obtenu via `auth_setup.py`                                |
| `START_DATE`            | var     | Date plancher absolue (`AAAA-MM-JJ`) : point de départ du 1er scan, jamais dépassée vers le bas |
| `SPOTIFY_PLAYLIST_NAME` | var     | Nom de la playlist (créée si absente)                           |
| `SPOTIFY_PLAYLIST_ID`   | var     | *(optionnel)* ID d'une playlist existante, prioritaire sur le nom |

---

## Notes

- **Abonnements = artistes suivis** (le « follow » Spotify).
- Le script ne récupère que les **propres sorties** des artistes
  (`album` + `single`), pas les compilations où ils apparaissent.
- Le **dédoublonnage** se fait au niveau des pistes par rapport au contenu actuel
  de la playlist : tu peux relancer sans risque de doublons.
- Modifier l'heure / la fréquence : édite la ligne `cron` dans
  [.github/workflows/sync.yml](.github/workflows/sync.yml).
