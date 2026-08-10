"""Trace lineage enums."""

from enum import StrEnum


class TraceCanonicalKind(StrEnum):
    """Discriminator for polymorphic `canonical_id` references."""

    RULE = "rule"
    OBJECT = "object"
    OBJECT_MEMBER = "object_member"
    ZONE = "zone"
    RULE_OPERAND = "rule_operand"
    ISSUE = "issue"


class TraceCanonicalRole(StrEnum):
    """Optional semantic sub-role stored as string in trace records."""

    # operands
    SRC_ZONE = "src_zone"
    DST_ZONE = "dst_zone"
    SRC_OBJECT = "src_object"
    DST_OBJECT = "dst_object"
    SERVICE = "service"

    # object internals
    HEADER = "header"
    MEMBER_REF = "member_ref"

    # zone derivation
    FROM_ACL_NAME = "from_acl_name"
    FROM_ACCESS_GROUP_BINDING = "from_access_group_binding"
