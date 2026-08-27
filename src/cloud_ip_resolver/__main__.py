"""Package entry point for ``python -m cloud_ip_resolver``.

Python executes this file when the package is run with ``-m``.  We delegate to
``cli.main`` so both the installed ``cloud-ip-resolver`` command and
``python -m cloud_ip_resolver`` follow exactly the same code path.
"""

from .cli import main

raise SystemExit(main())
