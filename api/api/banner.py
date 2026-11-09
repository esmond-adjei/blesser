"""The terminal wordmark printed when the API starts."""

from api import __version__

_ART = """\
  ██████╗ ██╗     ███████╗███████╗███████╗███████╗██████╗
  ██╔══██╗██║     ██╔════╝██╔════╝██╔════╝██╔════╝██╔══██╗
  ██████╔╝██║     █████╗  ███████╗███████╗█████╗  ██████╔╝
  ██╔══██╗██║     ██╔══╝  ╚════██║╚════██║██╔══╝  ██╔══██╗
  ██████╔╝███████╗███████╗███████║███████║███████╗██║  ██║
  ╚═════╝ ╚══════╝╚══════╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝"""


def banner() -> str:
    """The full startup banner, version included."""
    return (
        f"{_ART}\n"
        "       opportunities, found and checked by agents\n"
        f"                     v{__version__} · /docs"
    )


def print_banner() -> None:
    print(banner(), flush=True)
