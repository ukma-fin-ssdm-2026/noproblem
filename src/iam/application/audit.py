"""Журнал подій безпеки IAM.

Події безпеки пишуться в окремий логер ``notely.security``, а не в
загальний журнал застосунку. Так їх можна направити в окремий файл чи
систему моніторингу (вимога «спроби неавторизованого доступу
логуються», Project-Description 4.5; сценарій S-SEC-002).

Правила запису (OWASP Logging Cheat Sheet):

* ніколи не логувати паролі, токени, хеші;
* email — персональні дані, тому замість нього пишемо ``user_id``;
* фіксувати і успіхи, і відмови, щоб бачити атаки перебором.
"""

from __future__ import annotations

import logging

security_log = logging.getLogger("notely.security")


# File was created by Claude (AI-assisted); review by a team member pending.
