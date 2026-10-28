"""Run the standalone UDS Agent; Browser Runner has a separate process entrypoint."""

from .agent import main

if __name__ == "__main__":
    main()
