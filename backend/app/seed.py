from sqlalchemy.orm import Session

from .extensions import sync_builtin
from .models import Customer, SavedSession
from .settings_store import get_value, set_value


def seed(db: Session) -> None:
    sync_builtin(db)
    if not get_value(db, "seeded"):
        lab = Customer(
            name="Lab",
            color="#3d9cf0",
            notes="Built-in playground. No real devices required.",
        )
        acme = Customer(
            name="Acme Manufacturing",
            color="#ffb020",
            notes="Sample customer. Edit hosts/passwords to use on the plant floor.",
        )
        city = Customer(
            name="City of Riverside",
            color="#3dd68c",
            notes="Sample municipal customer.",
        )
        db.add_all([lab, acme, city])
        db.flush()
        db.add_all(
            [
                SavedSession(
                    customer_id=lab.id,
                    name="Local Shell",
                    kind="local",
                    device_type="linux",
                    notes="Warp-style local bash inside NTerm.",
                ),
                SavedSession(
                    customer_id=lab.id,
                    name="Cisco IOS Simulator",
                    kind="simulator",
                    device_type="cisco_ios",
                    notes="Practice broadcast, snippets, and the config analyzer.",
                ),
                SavedSession(
                    customer_id=lab.id,
                    name="PAN-OS Simulator",
                    kind="simulator",
                    device_type="paloalto",
                ),
                SavedSession(
                    customer_id=lab.id,
                    name="FortiOS Simulator",
                    kind="simulator",
                    device_type="fortinet",
                ),
                SavedSession(
                    customer_id=acme.id,
                    name="Core-SW-01",
                    kind="ssh",
                    device_type="cisco_ios",
                    host="10.10.10.2",
                    username="cisco",
                    notes="Plant core. Set the real password in the session editor.",
                ),
                SavedSession(
                    customer_id=acme.id,
                    name="Edge-FW",
                    kind="ssh",
                    device_type="fortinet",
                    host="10.10.10.1",
                    username="admin",
                ),
                SavedSession(
                    customer_id=city.id,
                    name="DC-PA-VM",
                    kind="ssh",
                    device_type="paloalto",
                    host="10.8.8.10",
                    username="admin",
                ),
            ]
        )
        set_value(db, "seeded", "1")
        db.commit()

    from .config import DATA_DIR

    sample = DATA_DIR / "tftp" / "ztp" / "cisconet.cfg"
    if not sample.exists():
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_text(
            "hostname ZTP-SWITCH\n"
            "ip domain-name lab.nterm\n"
            "logging host 10.88.0.1\n"
            "end\n",
            encoding="utf-8",
        )
    readme = DATA_DIR / "tftp" / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Drop IOS images and configs here. Devices can `copy tftp://<nterm-ip>/file flash:`.\n",
            encoding="utf-8",
        )
