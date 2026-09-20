# SPDX-License-Identifier: GPL-3.0-or-later
#
# Backwards-compatibility wrapper for mascota.py -> moka.py

from moka import main, parse_args

if __name__ == "__main__":
    main()
