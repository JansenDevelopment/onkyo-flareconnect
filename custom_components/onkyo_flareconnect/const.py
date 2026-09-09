"""Constanten voor de Onkyo FlareConnect-integratie."""

DOMAIN = "onkyo_flareconnect"

CONF_HOSTS = "hosts"

# Onkyo-toestellen accepteren maar EEN eISCP-verbinding tegelijk. Elke keer dat wij er een
# openen, verliest de officiele onkyo-integratie de hare en herverbindt hij - wat zichtbaar is
# als knipperende media-info. Groepen veranderen alleen als iemand ze wijzigt, dus poll rustig;
# na onze eigen join/unjoin verversen we sowieso meteen.
DEFAULT_SCAN_INTERVAL = 300  # seconden

# Services
SERVICE_JOIN = "join"
SERVICE_UNJOIN = "unjoin"
SERVICE_SEND_COMMAND = "send_command"

ATTR_SOURCE = "source"
ATTR_MEMBERS = "members"
ATTR_GROUP_ID = "group_id"
ATTR_MAX_DELAY = "max_delay"
ATTR_HOST = "host"
ATTR_COMMANDS = "commands"
ATTR_DELAY = "delay"
