"""
À lancer UNE SEULE FOIS en local pour obtenir un refresh token Spotify.

Le refresh token obtenu sera ensuite enregistré comme secret GitHub
(SPOTIFY_REFRESH_TOKEN) afin que la synchronisation tourne toute seule.

Prérequis : un fichier .env (copié depuis .env.example) avec au minimum
SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET et SPOTIFY_REDIRECT_URI renseignés.
"""

import os

import spotipy
from spotipy.oauth2 import SpotifyOAuth

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

SCOPES = "user-follow-read playlist-read-private playlist-modify-private playlist-modify-public"


def main():
    auth = SpotifyOAuth(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SCOPES,
        open_browser=True,
        cache_handler=spotipy.cache_handler.MemoryCacheHandler(),
    )

    url = auth.get_authorize_url()
    print("\n1) Ouvre cette URL dans ton navigateur et autorise l'application :\n")
    print("   " + url)
    print("\n2) Tu seras redirigé vers une URL du type :")
    print("   http://127.0.0.1:8888/callback?code=XXXXXXXX")
    print("   (la page peut afficher une erreur de connexion, c'est NORMAL —")
    print("    seule l'URL dans la barre d'adresse compte).")
    print("\n3) Copie-colle ci-dessous l'URL COMPLÈTE de redirection.\n")

    redirected = input("URL de redirection : ").strip()
    code = auth.parse_response_code(redirected)
    token = auth.get_access_token(code, as_dict=True, check_cache=False)

    print("\n=== SUCCÈS ===")
    print("Enregistre cette valeur comme secret GitHub « SPOTIFY_REFRESH_TOKEN » :\n")
    print(token["refresh_token"])
    print()


if __name__ == "__main__":
    main()
