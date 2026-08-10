from enum import StrEnum


class SdwanZoneType(StrEnum):

    LAN = "lan"
    WAN = "wan"
    WGD = "wgd"
    WGRA = "wgra"


class SdwanServiceL4Proto(StrEnum):

    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    ANY = "any"
    IP_IP = "ip_ip"


class SdwanAddrObjectType(StrEnum):  # imported from sdwan integration schema

    PREFIX = "prefix"
    HOST = "host"
    FQDN = "fqdn"
    IP_RANGE = "ip_range"
    NETWORK = "network"
    ADDR_GROUP = "addr_group"


class SdwanDeviceObjectType(StrEnum):

    DEVICE = "device"
    GROUP = "group"
