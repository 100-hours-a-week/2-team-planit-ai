import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    import uvicorn
    from app.core.config import settings

    uvicorn.run(
        app="app.main:app",
        host=settings.host,
        port=settings.port,
        loop="uvloop",
    )

if __name__ == "__main__":
    main()
