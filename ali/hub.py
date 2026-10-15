"""Ulangan qurilmalar (telefon, kompyuter brauzeri) bilan aloqa markazi.

Brain alohida oqimda (thread) ishlaydi, WebSocket esa asyncio'da - shu modul ular orasida ko'prik.
Ko'nikmalar bu yerdan foydalanib: tasdiq so'raydi, telefonga buyruq yuboradi, joylashuvni oladi.
"""
import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass, field

log = logging.getLogger("ali.hub")


class Listener:
    """Brauzerdan tashqari kanallar (masalan Telegram) uchun interfeys. Metodlar brain oqimidan chaqiriladi."""

    def on_confirm(self, cid: str, name: str, args: dict) -> None: ...
    def on_confirm_closed(self, cid: str) -> None: ...
    def on_notify(self, text: str) -> None: ...
    def on_answer(self, question: str, answer: str, source: str) -> None: ...


@dataclass
class Device:
    id: str
    kind: str  # phone | desktop
    ws: object
    location: dict | None = None


@dataclass
class Hub:
    loop: asyncio.AbstractEventLoop | None = None
    devices: dict[str, Device] = field(default_factory=dict)
    last_location: dict | None = None
    listeners: list[Listener] = field(default_factory=list)
    _pending: dict[str, tuple[threading.Event, list]] = field(default_factory=dict)

    # --- qurilmalar ---
    def add(self, ws, kind: str) -> Device:
        device = Device(id=uuid.uuid4().hex[:8], kind=kind, ws=ws)
        self.devices[device.id] = device
        return device

    def remove(self, device_id: str) -> None:
        self.devices.pop(device_id, None)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.devices.values():
            counts[d.kind] = counts.get(d.kind, 0) + 1
        return counts

    # --- xabar yuborish (istalgan oqimdan) ---
    def broadcast(self, payload: dict, kind: str | None = None) -> int:
        targets = [d for d in list(self.devices.values()) if kind is None or d.kind == kind]
        for d in targets:
            self._send(d, payload)
        return len(targets)

    def _send(self, device: Device, payload: dict) -> None:
        if not self.loop or self.loop.is_closed():
            return
        coro = device.ws.send_json(payload)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    # --- tasdiq ---
    def confirm(self, name: str, args: dict, timeout: float = 120) -> bool:
        """Xavfli amal uchun barcha qurilmalarda tasdiq oynasini ochadi va javobni kutadi."""
        if not self.devices and not self.listeners:
            return False
        cid = uuid.uuid4().hex[:8]
        event, answer = threading.Event(), [False]
        self._pending[cid] = (event, answer)
        self.broadcast({"type": "confirm", "id": cid, "name": name, "args": args})
        self._each_listener("on_confirm", cid, name, args)
        event.wait(timeout)
        self._pending.pop(cid, None)
        self.broadcast({"type": "confirm_closed", "id": cid})
        self._each_listener("on_confirm_closed", cid)
        return answer[0]

    def resolve_confirm(self, cid: str, ok: bool) -> None:
        if cid in self._pending:
            event, answer = self._pending[cid]
            answer[0] = ok
            event.set()

    # --- bildirishnoma (eslatmalar va h.k.) ---
    def notify(self, text: str, kind: str | None = None) -> int:
        """Brauzerlarga va barcha tinglovchilarga (Telegram) xabar yuboradi."""
        n = self.broadcast({"type": "notify", "text": text}, kind=kind)
        self._each_listener("on_notify", text)
        return n + len(self.listeners)

    def _each_listener(self, method: str, *args) -> None:
        for listener in list(self.listeners):
            try:
                getattr(listener, method)(*args)
            except Exception:
                log.exception("Listener xatosi: %s", method)

    # --- joylashuv ---
    def set_location(self, device_id: str, location: dict) -> None:
        if device_id in self.devices:
            self.devices[device_id].location = location
        self.last_location = location


hub = Hub()
