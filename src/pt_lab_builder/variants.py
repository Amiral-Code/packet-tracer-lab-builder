"""Every student gets a different lab: consistent re-addressing of a whole spec.

A variant is the same lab with its private IPv4 space moved: every occurrence in the spec text (addressing table,
configurations, ACL and OSPF wildcards' networks, grade statements, connectivity tests, instructions) changes
together, so the lab stays self-consistent. Mapping works on the octet that keeps wider prefixes intact:

- 10.A.x.x       -> 10.A'.x.x        (an ACL "10.10.0.0 0.0.255.255" still covers every 10.10 network)
- 172.B.x.x      -> 172.B'.x.x       (B' stays in 16-31)
- 192.168.C.x    -> 192.168.C'.x     (except 192.168.0, a home router's fixed LAN)

Documentation ranges (192.0.2, 198.51.100, 203.0.113), public addresses and IPv6 are left alone. Each variant is
checked with the normal spec check and self-check (answer full marks, start not, every fault breaks something)
before it is written; a mapping that fails is retried with another draw.
"""
import random
import re
import tomllib

ADDR = re.compile(r"(?<![\d.])(10|172|192)\.(\d{1,3})\.(\d{1,3})(?=\.\d)")


def _used(text):
    tens, sixteens, one92 = set(), set(), set()
    for a, b, c in ADDR.findall(text):
        b, c = int(b), int(c)
        if a == "10":
            tens.add(b)
        elif a == "172" and 16 <= b <= 31:
            sixteens.add(b)
        elif a == "192" and b == 168:
            one92.add(c)
    return tens, sixteens, one92


def mapping(text, rng, keep_192_168_0=False):
    """{(first, second[, third]) prefix: new} for one variant, injective within each range."""
    tens, sixteens, one92 = _used(text)
    m10 = dict(zip(sorted(tens), rng.sample([x for x in range(1, 255)], len(tens))))
    m172 = dict(zip(sorted(sixteens), rng.sample(range(16, 32), len(sixteens))))
    pool = [x for x in range(1, 255) if not keep_192_168_0 or x != 0]
    m192 = dict(zip(sorted(one92), rng.sample(pool, len(one92))))
    if keep_192_168_0 and 0 in one92:
        m192[0] = 0
        taken = {v for k, v in m192.items() if k != 0}
        if 0 in taken:                                   # never move another network onto 192.168.0
            free = [x for x in range(1, 255) if x not in taken]
            for k, v in m192.items():
                if k != 0 and v == 0:
                    m192[k] = free.pop()
    return m10, m172, m192


def apply(text, maps):
    m10, m172, m192 = maps

    def sub(m):
        a, b, c = m.group(1), int(m.group(2)), int(m.group(3))
        if a == "10" and b in m10:
            return f"10.{m10[b]}.{c}"
        if a == "172" and b in m172:
            return f"172.{m172[b]}.{c}"
        if a == "192" and b == 168 and c in m192:
            return f"192.168.{m192[c]}"
        return m.group(0)
    return ADDR.sub(sub, text)


def make(spec_text, index, seed):
    """The text of variant `index` (1-based) of a spec, with its id and title marked."""
    spec = tomllib.loads(spec_text)
    keep0 = any(d.get("model") in ("home-router", "wrt300n") for d in spec.get("device", []))
    rng = random.Random(f"{seed}:{index}")
    text = apply(spec_text, mapping(spec_text, rng, keep0))
    lab_id = spec["lab"]["id"]
    text = re.sub(r'(?m)^id = "' + re.escape(lab_id) + '"', f'id = "{lab_id}-v{index:02d}"', text, count=1)
    text = re.sub(r'(?m)^(title = ".*?)"$', rf'\1 (variant {index:02d})"', text, count=1)
    return text
