TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell_command",
            "description": (
                "Draft ONE shell command for a Linux/Unix shell or Windows PowerShell "
                "session. Use for local shell and Linux hosts. Prefer read-only "
                "investigation. Never chain destructive operations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The exact command to run. One command."},
                    "explanation": {"type": "string", "description": "One short line: what it does."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_interface_ip",
            "description": "Set an IPv4 address/mask on one interface. Small change only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "interface": {"type": "string"},
                    "cidr": {"type": "string", "description": "e.g. 1.1.1.1/24"},
                },
                "required": ["interface", "cidr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dhcp_pool",
            "description": "Create a small DHCP pool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "cidr": {"type": "string"},
                    "gateway": {"type": "string"},
                    "dns": {"type": "string"},
                },
                "required": ["cidr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "palo_rule",
            "description": "Add one Palo Alto security rule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "from_zone": {"type": "string"},
                    "to_zone": {"type": "string"},
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                    "app": {"type": "string"},
                    "action": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forti_vip",
            "description": "Create one FortiGate VIP / port forward.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "extip": {"type": "string"},
                    "mappedip": {"type": "string"},
                    "port": {"type": "string"},
                },
                "required": ["extip", "mappedip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "static_route",
            "description": "Add one static route.",
            "parameters": {
                "type": "object",
                "properties": {"cidr": {"type": "string"}, "nexthop": {"type": "string"}},
                "required": ["cidr", "nexthop"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_status",
            "description": "Read-only interface/status show command.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SCHEMA_VERSION = "nterm-tools-v1"
