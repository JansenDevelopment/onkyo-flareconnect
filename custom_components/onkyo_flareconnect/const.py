"""Constanten voor de Onkyo FlareConnect-integratie."""

DOMAIN = "onkyo_flareconnect"

CONF_HOSTS = "hosts"

# BEWUST GEEN PERIODIEKE POLLING.
# De officiele onkyo-integratie houdt een eISCP-verbinding open waarover de toestellen hun
# statuswijzigingen pushen (volume, aan/uit, bron). Openen wij daarnaast een verbinding, dan
# verliest zij de hare, mist ze pushberichten en moet ze bij het herverbinden de hele staat
# opnieuw opvragen - zichtbaar als knipperende media-info.
# Groepen veranderen alleen als iemand ze wijzigt, dus we verversen bij het opstarten, na onze
# eigen join/unjoin, en verder alleen als erom gevraagd wordt (service `refresh`).
SCAN_INTERVAL = None

# Services
SERVICE_JOIN = "join"
SERVICE_UNJOIN = "unjoin"
SERVICE_SEND_COMMAND = "send_command"
SERVICE_REFRESH = "refresh"

ATTR_SOURCE = "source"
ATTR_MEMBERS = "members"
ATTR_GROUP_ID = "group_id"
ATTR_MAX_DELAY = "max_delay"
ATTR_HOST = "host"
ATTR_COMMANDS = "commands"
ATTR_DELAY = "delay"
