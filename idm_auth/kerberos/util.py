import enum


class KerberosAttribute(enum.Enum):
    DISALLOW_POSTDATED = 0x00000001
    DISALLOW_FORWARDABLE = 0x00000002
    DISALLOW_TGT_BASED = 0x00000004
    DISALLOW_RENEWABLE = 0x00000008
    DISALLOW_PROXIABLE = 0x00000010
    DISALLOW_DUP_SKEY = 0x00000020
    DISALLOW_ALL_TIX = 0x00000040
    REQUIRES_PRE_AUTH = 0x00000080
    REQUIRES_HW_AUTH = 0x00000100
    REQUIRES_PWCHANGE = 0x00000200
    UNKNOWN_0x00000400 = 0x00000400
    UNKNOWN_0x00000800 = 0x00000800
    DISALLOW_SVR = 0x00001000
    PWCHANGE_SERVICE = 0x00002000
    SUPPORT_DESMD5 = 0x00004000
    NEW_PRINC = 0x00008000
    OK_AS_DELEGATE = 0x00010000
    TRUSTED_FOR_DELEGATION = 0x00020000
    ALLOW_KERBEROS4 = 0x00040000
    ALLOW_DIGEST = 0x00080000
