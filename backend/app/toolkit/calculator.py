import ipaddress


def analyze_cidr(cidr: str, split: int | None = None) -> dict:
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = list(net.hosts())
    first = str(hosts[0]) if hosts else str(net.network_address)
    last = str(hosts[-1]) if hosts else str(net.network_address)
    result = {
        "network": str(net.network_address),
        "broadcast": str(net.broadcast_address) if net.version == 4 else None,
        "netmask": str(net.netmask) if net.version == 4 else None,
        "wildcard": str(net.hostmask) if net.version == 4 else None,
        "prefix": net.prefixlen,
        "version": net.version,
        "num_addresses": net.num_addresses,
        "usable_hosts": max(net.num_addresses - 2, 0) if net.version == 4 and net.prefixlen < 31 else net.num_addresses,
        "first_host": first,
        "last_host": last,
        "cisco_wildcard": str(net.hostmask) if net.version == 4 else None,
        "subnets": [],
    }
    if split and split > net.prefixlen and net.version == 4:
        result["subnets"] = [
            {
                "cidr": str(sub),
                "network": str(sub.network_address),
                "broadcast": str(sub.broadcast_address),
                "first_host": str(list(sub.hosts())[0]) if list(sub.hosts()) else str(sub.network_address),
                "last_host": str(list(sub.hosts())[-1]) if list(sub.hosts()) else str(sub.network_address),
            }
            for sub in list(net.subnets(new_prefix=split))[:64]
        ]
    return result
