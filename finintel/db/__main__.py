import sys

from finintel.db.migrate import main

raise SystemExit(main(sys.argv[1:]))
