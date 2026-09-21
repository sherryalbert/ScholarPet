import sys

from scholarpet.app import main

if __name__ == '__main__':
    if '--selftest' in sys.argv:
        from scholarpet.selftest import run
        raise SystemExit(run())
    raise SystemExit(main())
