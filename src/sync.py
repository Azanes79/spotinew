"""
spotinew — Ajoute automatiquement les nouvelles sorties des artistes suivis
sur Spotify dans une playlist dédiée, à partir d'une date donnée (START_DATE).

Conçu pour tourner sans interaction (GitHub Actions) grâce à un refresh token.

Logique :
  1. Récupère les artistes suivis (scope user-follow-read).
  2. Détermine la fenêtre de scan à partir de la date du dernier scan,
     persistée dans state.json (ou START_DATE au tout premier passage).
  3. Pour chaque artiste, liste ses albums/singles parus dans la fenêtre.
  4. Ajoute à la playlist les pistes absentes (dédoublonnage).
  5. Enregistre la date de ce scan dans state.json pour le prochain passage.

La date du dernier scan est stockée dans un fichier (state.json), indépendamment
du contenu de la playlist : tu peux donc écouter puis supprimer les titres de la
playlist sans que le scan reparte de START_DATE.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

import spotipy
from spotipy.oauth2 import SpotifyOAuth

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv est optionnel (absent en CI, vars déjà injectées)
    pass

SCOPES = "user-follow-read playlist-read-private playlist-modify-private playlist-modify-public"


def env(name, default=None, required=False):
    # Une variable GitHub Actions non définie est transmise comme chaîne vide :
    # on la traite donc comme absente et on retombe sur le défaut.
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        val = default
    if required and not val:
        sys.exit(f"[ERREUR] Variable d'environnement manquante : {name}")
    return val


def state_path():
    return env("STATE_FILE", "state.json")


def load_last_scan():
    """Lit la date du dernier scan depuis state.json (None si absent/illisible)."""
    try:
        with open(state_path(), encoding="utf-8") as f:
            return date.fromisoformat(json.load(f)["last_scan"])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return None


def save_last_scan(scan_date):
    """Écrit la date du dernier scan dans state.json."""
    with open(state_path(), "w", encoding="utf-8") as f:
        json.dump({"last_scan": scan_date.isoformat()}, f, indent=2)
        f.write("\n")


def get_client():
    """Construit un client Spotify authentifié à partir du refresh token."""
    auth = SpotifyOAuth(
        client_id=env("SPOTIFY_CLIENT_ID", required=True),
        client_secret=env("SPOTIFY_CLIENT_SECRET", required=True),
        redirect_uri=env("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SCOPES,
        open_browser=False,
        cache_handler=spotipy.cache_handler.MemoryCacheHandler(),
    )
    token_info = auth.refresh_access_token(env("SPOTIFY_REFRESH_TOKEN", required=True))
    return spotipy.Spotify(
        auth=token_info["access_token"],
        requests_timeout=30,
        retries=5,
        status_retries=5,
        backoff_factor=0.5,
    )


def parse_release_date(release_date, precision):
    """Convertit une release_date Spotify (année / mois / jour) en objet date."""
    parts = (release_date or "").split("-")
    try:
        year = int(parts[0])
    except (ValueError, IndexError):
        return None
    month = int(parts[1]) if len(parts) > 1 and precision != "year" else 1
    day = int(parts[2]) if len(parts) > 2 and precision == "day" else 1
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 1, 1)


def get_followed_artists(sp):
    """Récupère tous les artistes suivis (pagination par curseur)."""
    artists = []
    after = None
    while True:
        page = sp.current_user_followed_artists(limit=50, after=after)["artists"]
        items = page.get("items", [])
        artists.extend(items)
        after = (page.get("cursors") or {}).get("after")
        if not after or not items:
            break
    return artists


def get_recent_albums(sp, artist_id, floor, market):
    """Albums/singles de l'artiste parus à partir de `floor`.

    Dédoublonne par nom (en minuscules) pour éviter les versions multi-marchés.
    """
    albums = {}
    offset = 0
    while True:
        page = sp.artist_albums(
            artist_id,
            include_groups="album,single",
            country=market,
            limit=50,
            offset=offset,
        )
        items = page.get("items", [])
        for alb in items:
            rd = parse_release_date(alb.get("release_date"), alb.get("release_date_precision"))
            if not rd or rd < floor:
                continue
            key = alb["name"].strip().lower()
            if key not in albums:
                albums[key] = (rd, alb["name"], alb["id"])
        if page.get("next"):
            offset += len(items)
        else:
            break
    return list(albums.values())


def get_album_track_uris(sp, album_id):
    """Liste les pistes d'un album : (id, uri, nom)."""
    tracks = []
    results = sp.album_tracks(album_id, limit=50)
    while results:
        for t in results.get("items", []):
            if t and t.get("id"):
                tracks.append((t["id"], t["uri"], t["name"]))
        results = sp.next(results) if results.get("next") else None
    return tracks


def get_playlist_track_ids(sp, playlist_id):
    """IDs des pistes actuellement présentes dans la playlist (dédoublonnage)."""
    ids = set()
    results = sp.playlist_items(
        playlist_id, fields="items(track(id)),next", limit=100, additional_types=("track",)
    )
    while results:
        for it in results.get("items", []):
            t = it.get("track")
            if t and t.get("id"):
                ids.add(t["id"])
        results = sp.next(results) if results.get("next") else None
    return ids


def find_or_create_playlist(sp, me):
    """Renvoie l'ID de la playlist cible (par ID explicite, sinon par nom, sinon créée)."""
    playlist_id = env("SPOTIFY_PLAYLIST_ID")
    if playlist_id:
        return playlist_id

    name = env("SPOTIFY_PLAYLIST_NAME", "Nouveautés abonnements")
    user_id = me["id"]
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        for pl in page["items"]:
            if pl and pl["name"] == name and pl["owner"]["id"] == user_id:
                return pl["id"]
        if page.get("next"):
            offset += len(page["items"])
        else:
            break

    print(f"[INFO] Playlist « {name} » introuvable — création…")
    pl = sp.user_playlist_create(
        user_id,
        name,
        public=False,
        description="Nouveautés des artistes suivis — alimentée automatiquement par spotinew.",
    )
    return pl["id"]


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def notify_discord(webhook_url, added, artists_count, floor, today, error=None):
    """Envoie un résumé du sync sur un webhook Discord."""
    if not webhook_url:
        return
    if error:
        color = 0xED4245  # rouge Discord
        title = "spotinew — sync échoué"
        description = f"Une erreur s'est produite :\n```\n{error}\n```"
    else:
        color = 0x1DB954  # vert Spotify
        title = "spotinew — sync terminé"
        description = (
            f"**{added}** nouveau(x) titre(s) ajouté(s)\n"
            f"Fenêtre : {floor.isoformat()} → {today.isoformat()}\n"
            f"Artistes scannés : {artists_count}"
        )
    payload = json.dumps({
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
        }]
    }).encode()
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "spotinew/1.0"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.URLError as exc:
        print(f"[WARN] Impossible d'envoyer la notification Discord : {exc}")


def main():
    discord_webhook = env("DISCORD_WEBHOOK_URL")
    start_date = date.fromisoformat(env("START_DATE", required=True))

    sp = get_client()
    me = sp.me()
    market = me.get("country")
    playlist_id = find_or_create_playlist(sp, me)
    print(f"[INFO] Playlist cible : {playlist_id}")

    existing = get_playlist_track_ids(sp, playlist_id)
    print(f"[INFO] {len(existing)} titre(s) déjà dans la playlist.")

    # Fenêtre de scan : on repart du LENDEMAIN du dernier scan (pour ne pas
    # reproposer un titre déjà traité), sans jamais descendre sous START_DATE.
    # state.json étant indépendant de la playlist, vider celle-ci ne réinitialise
    # pas le point de départ.
    last_scan = load_last_scan()
    if last_scan:
        floor = max(start_date, last_scan + timedelta(days=1))
        print(f"[INFO] Dernier scan : {last_scan.isoformat()} → "
              f"sorties à partir de {floor.isoformat()}.")
    else:
        floor = start_date
        print(f"[INFO] Aucun scan précédent → depuis START_DATE "
              f"({floor.isoformat()}).")

    artists = get_followed_artists(sp)
    print(f"[INFO] {len(artists)} artiste(s) suivi(s).")

    seen = set(existing)
    new_tracks = []  # (release_date, uri)
    for i, artist in enumerate(artists, 1):
        albums = get_recent_albums(sp, artist["id"], floor, market)
        added_here = 0
        for _rd, _name, album_id in albums:
            for tid, uri, _tname in get_album_track_uris(sp, album_id):
                if tid not in seen:
                    seen.add(tid)
                    new_tracks.append((_rd, uri))
                    added_here += 1
        if albums:
            print(f"  [{i}/{len(artists)}] {artist['name']} — "
                  f"{len(albums)} sortie(s), {added_here} nouveau(x) titre(s)")

    # Ordre chronologique : les plus anciennes nouveautés en premier.
    new_tracks.sort(key=lambda x: x[0])
    uris = [uri for _, uri in new_tracks]

    if uris:
        for batch in chunked(uris, 100):
            sp.playlist_add_items(playlist_id, batch)
        print(f"[OK] {len(uris)} titre(s) ajouté(s) à la playlist.")
    else:
        print("[OK] Aucune nouveauté à ajouter.")

    # On enregistre la date de ce scan APRÈS succès, pour repartir de là au
    # prochain passage (même si la playlist est vidée entre-temps).
    today = date.today()
    save_last_scan(today)
    print(f"[INFO] Date du dernier scan enregistrée : {today.isoformat()}")

    notify_discord(discord_webhook, len(uris), len(artists), floor, today)


if __name__ == "__main__":
    main()
