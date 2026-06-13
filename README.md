# spotinew

Ajoute automatiquement, chaque jour, les **nouvelles sorties de tes artistes
suivis sur Spotify** dans une **playlist dédiée**, à partir d'une date donnée.

Tourne tout seul dans le cloud via **GitHub Actions** (gratuit, même PC éteint),
ou en **self-hosting** via Docker.

---

## Comment ça marche

À chaque exécution, le script :

1. récupère la liste de tes **artistes suivis** ;
2. détermine la **fenêtre de scan** : il repart du **lendemain du dernier scan**
   (date mémorisée dans `state.json`) ; au tout premier passage, il part de
   `START_DATE` ;
3. liste leurs **albums / singles** parus dans cette fenêtre ;
4. récupère les **pistes** et les **ajoute à la playlist** en évitant les doublons ;
5. **enregistre la date de ce scan** dans `state.json` (committé par le workflow GitHub Actions, ou persisté dans un volume Docker en self-hosting).

> ⏱️ **Reprise incrémentale persistante.** La date du dernier scan est stockée
> dans [`state.json`](state.json), **indépendamment de la playlist**. Tu peux donc
> écouter puis **supprimer les titres** de la playlist pour faire ton tri : le
> prochain scan repartira quand même du dernier scan, et **jamais** de
> `START_DATE`. Le scan repart du *lendemain* du dernier scan pour ne pas te
> reproposer un titre déjà écouté et supprimé.

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

### Étape 4 — Automatiser

Deux options selon ton infrastructure :

#### Option A — GitHub Actions (cloud, gratuit)

1. Crée un dépôt GitHub et pousse ce projet.
2. Dans **Settings → Secrets and variables → Actions** :
   - Onglet **Secrets** → *New repository secret* :
     - `SPOTIFY_CLIENT_ID`
     - `SPOTIFY_CLIENT_SECRET`
     - `SPOTIFY_REFRESH_TOKEN`
     - `DISCORD_WEBHOOK_URL` *(optionnel)* — URL du webhook Discord pour recevoir un résumé après chaque sync
   - Onglet **Variables** → *New repository variable* :
     - `START_DATE` → ex. `2026-01-01`
     - `SPOTIFY_PLAYLIST_NAME` → ex. `Nouveautés abonnements`
     - `SPOTIFY_PLAYLIST_ID` *(facultatif)* — pour cibler une playlist précise.
3. C'est tout. Le workflow tourne **chaque jour à 02:00 UTC (≈ 04:00 à Paris en été)**.
   Tu peux aussi le lancer à la main : onglet **Actions → spotinew → Run workflow**.

#### Option B — Self-hosting avec Docker

L'image est publiée automatiquement sur GitHub Container Registry à chaque push sur `main`.

1. Sur ton serveur, crée un fichier de secrets (une seule fois) :
   ```bash
   # /etc/spotinew.env  —  chmod 600
   SPOTIFY_CLIENT_ID=xxx
   SPOTIFY_CLIENT_SECRET=xxx
   SPOTIFY_REFRESH_TOKEN=xxx
   START_DATE=2026-01-01
   SPOTIFY_PLAYLIST_ID=xxx
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...  # optionnel
   ```

2. Crée un répertoire persistant pour `state.json` :
   ```bash
   mkdir -p /var/lib/spotinew
   ```

3. Lance le conteneur (à planifier via cron, systemd timer, etc.) :

   **Avec `docker run` :**
   ```bash
   docker run --rm \
     --env-file /etc/spotinew.env \
     -v /var/lib/spotinew:/data \
     ghcr.io/YOUR_GITHUB_USERNAME/spotinew:latest
   ```

   **Avec Docker Compose (`docker compose run spotinew`) :**
   ```yaml
   services:
     spotinew:
       image: ghcr.io/YOUR_GITHUB_USERNAME/spotinew:latest
       env_file: /etc/spotinew.env
       volumes:
         - /var/lib/spotinew:/data
   ```

> `state.json` est stocké dans `/var/lib/spotinew` et persisté entre les exécutions.
> Pour forcer un re-scan complet depuis `START_DATE`, supprime ce fichier.

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
| `DISCORD_WEBHOOK_URL`   | secret  | *(optionnel)* URL d'un webhook Discord — envoie un résumé après chaque sync |

---

## Notes

- **Abonnements = artistes suivis** (le « follow » Spotify).
- Le script ne récupère que les **propres sorties** des artistes
  (`album` + `single`), pas les compilations où ils apparaissent.
- Le **dédoublonnage** se fait au niveau des pistes par rapport au contenu actuel
  de la playlist : tu peux relancer sans risque de doublons.
- La date du dernier scan est dans [`state.json`](state.json), mis à jour
  automatiquement par le workflow GitHub Actions (commit quotidien) ou persisté
  dans le volume Docker. Pour **forcer un re-scan complet** depuis `START_DATE`,
  supprime simplement `state.json`.
- **Notifications Discord.** Si `DISCORD_WEBHOOK_URL` est défini, un message est
  envoyé dans le salon Discord ciblé à la fin de chaque sync, avec le nombre de
  titres ajoutés, la fenêtre de scan et le nombre d'artistes analysés. En cas
  d'échec de la notification, le sync n'est pas interrompu (avertissement dans
  les logs uniquement). Pour créer un webhook : **Paramètres du salon → Intégrations → Webhooks → Nouveau webhook**.
- ⚠️ **Droits du workflow.** Le workflow committe `state.json` ; il déclare déjà
  `permissions: contents: write`. Si le `git push` échoue, va dans
  **Settings → Actions → General → Workflow permissions** et coche
  **« Read and write permissions »**.
- Modifier l'heure / la fréquence : édite la ligne `cron` dans
  [.github/workflows/sync.yml](.github/workflows/sync.yml).
