def main():
    import uvicorn
    from app.core.confing import settings

    uvicorn.run(
        app="app.main:app",
        host=settings.host,
        port=settings.port,
        loop="uvloop",
    )

if __name__ == "__main__":
    main()
