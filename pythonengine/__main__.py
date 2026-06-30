"""CLI entrypoint."""
import uvicorn

from pythonengine.config.loader import load_config


def main() -> None:
    config = load_config()
    uvicorn.run("pythonengine.web.app:create_app", factory=True, host=config.engine.host,
                port=config.engine.port, log_config=None)


if __name__ == "__main__":
    main()
