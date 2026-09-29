"""Point d'entrée ASGI : `uvicorn app:app`. Toute la logique est dans le paquet `pai`."""

from pai.api.app import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
